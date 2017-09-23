import asyncio
import logging
#aiomysql是MySQL的python异步驱动程序，操作数据库要用到
import aiomysql

#输出信息，让你知道这个时间点程序在做什么
def log(sql,args=()):
	logging.info('SQL:%s'%sql)

#创建全局连接池，使每个HTTP请求都可以从连接池中直接获取数据库连接
#避免频繁地打开和关闭数据库连接

async def create_pool(loop,**kw):
	logging.info('create database connecgtion pool...')
	global __pool
	__pool = await aiomysql.create_pool(
		#下面就是创建数据库连接需要用到的一些参数，从**kw（关键字参数）中取出
		#ke.get的作用是，当没有传入参数时，默认参数即是get函数的第二项
		host = kw.get('host','localhost'),#数据库服务器的位置，默认设在本地
		port = kw.get('port',3306),#mysql的端口，默认为3306
		user = kw['user'],#登录用户名，通过关键字参数传进来
		password = kw['password'],#登录密码，通过关键字参数传进来
		db = kw['db'],#当前数据库名
		charset=kw.get('charset','utf8'),#设置编码格式，默认为utf8
		autocommit=kw.get('autocommit',True),#自动提交模式，设置默认开启
		maxsize = kw.get('maxsize',10),#最大连接数默认为10
		minsize = kw.get('minsize',1),#最小连接数
		loop = loop #传递消息循环对象，用于异步执行
	)

#将要执行的SQL语句封装成select函数，调用时只要传入SQL和sql所需的参数就好
#sql参数即为sql语句，args表示要搜索的参数
#size用于指定最大查询数量，不指定将返回全部结果


async def select(sql,args,size=None):
	log(sql,args)
	#声明全局变量，引用create_pool函数创建的__pool变量
	global __pool
	#用with语句可以封装清理(关闭conn)和处理异常
	async with __pool.get() as conn:
		async with conn.cursor(aiomysql.DictCursor) as cur:
			#从连接池获得一个数据库连接
				#cur = yield from conn.cursor(aiomysql.DictCursor)
				#设置执行语句，其中?为sql语句的占位符，而%s为python的占位符，这里做下转换
			await cur.execute(sql.replace('?','%s'), args or ())
				#如果指定了查询数量则返回指定的查询数量，否则返回全部查询
			if size:
				rs = await cur.fetchmany(size)
			else:
				rs = await cur.fetchall()
		
		logging.info('rows returned:%s'%len(rs))
		return rs            #返回结果集

#要执行INSERT、UPDATE、DELETE语句，定义一个通用的execute()函数
async def execute(sql,args,autocommit=True):
	log(sql)
	async with __pool.get() as conn:
		try:
			async with conn.cursor(aiomysql.DictCursor) as cur:
			#cur = yield from conn.cursor()
				await cur.execute(sql.replace('?','%s'),args)
				affected = cur.rowcount    #返回受影响行数
			if not autocommit:
				await conn.commit()
		except BaseException as e:
			if not autocommit:
				await conn.rollback()
			raise
		return affected

#这个函数在元类中被引用，作用是创建一定数量的占位符
def create_args_string(num):
	L = []
	for n in range(num):
		L.append('?')
	return ','.join(L)

#====================================Field定义域区======================================
#父定义域，可以被其他定义域继承
class Field(object):
	def __init__(self,name,column_type,primary_key,default):
		self.name = name
		self.column_type = column_type
		self.primary_key = primary_key
		self.default = default

	#定制输出信息为 类名，列的类型，列名
	def __str__(self):
		return '<%s,%s,%s>'%(self.__class__.__name__,self.column_type,self.name)

class StringField(Field):
	def __init__(self,name=None,primary_key=False,default=None,ddl='varchar(100)'):
		super().__init__(name,ddl,primary_key,default)

class BooleanField(Field):
	def __init__(self,name=None,default=False):
		super().__init__(name,'boolean',False,default)

class IntergerField(Field):
	def __init__(self,name=None,primary_key=False,default=0):
		super().__init__(name,'bigint',primary_key,default)

class FloatField(Field):
	def __init__(self,name=None,default=None):
		super().__init__(name,'text',False,default)
class TextField(Field):
	def __init__(self,name=None,default=None):
		super().__init__(name,'text',False,default)

		

#编写元类
class ModelMetaclass(type):
	def __new__(cls,name,bases,attrs):
		#排除Model类本身
		if name=='Model':
			return type.__new__(cls,name,bases,attrs)
		#获取table名称
		tableName = attrs.get('__table__',None) or name
		logging.info('found model:%s(table:%s)'%(name,tableName))
		#获取所有定义域中的属性和主键
		mappings = dict()
		fields = []
		primaryKey = None
		for k, v in attrs.items():
			if isinstance(v,Field):
				logging.info('found mapping:%s ==> %s'%(k,v))
				mappings[k] = v
				#先判断找到的映射是不是主键
				if v.primary_key:
					if primaryKey:#若主键已存在，又找到一个主键将报错
						raise StandardError('Duplicate primary key for field:%s'%k)
					primaryKey = k
				else:
					fields.append(k)
		#如果没有找到主键，也会报错
		if not primaryKey:
			raise StandardError('Primary key not found.')
		#定义域中的key值已经添加到fields里了，就要在attrs中删除，避免重名导致运行时错误
		for k in mappings.keys():
			attrs.pop(k)
		#将非主键的属性变形，放入escaped_fields中，方便sql语句的书写
		escaped_fields = list(map(lambda f:'`%s`'%f,fields))
		attrs['__mappings__'] = mappings  #保存属性和列的映射关系
		attrs['__table__'] = tableName    #表名
		attrs['__primary_key__'] = primaryKey  #主键属性名
		attrs['__fields__'] = fields   #除主键外的属性名
		#构造默认的select，insert，update和delete语句:
		attrs['__select__'] = 'select `%s`,%s from `%s`'%(primaryKey,','.join(escaped_fields),tableName)
		attrs['__insert__'] = 'insert into `%s`(%s,`%s`) values(%s)'%(tableName,','.join(escaped_fields),primaryKey,create_args_string(len(escaped_fields)+1))
		attrs['__update__'] = 'update `%s` set %s where `%s`=?'%(tableName,','.join(map(lambda f:'`%s`=?'%(mappings.get(f).name or f),fields)),primaryKey)
		attrs['__delete__'] = 'delete from `%s` where `%s`=?'%(tableName,primaryKey)
		return type.__new__(cls,name,bases,attrs)

#==========================================Model基类区=======================================================
#定义所有ORM映射的基类Model，使他既可以想字典那样通过[]访问key值，也可以通过.访问key值
#继承dict是为了使用方便，例如对象实例user['id']即可轻松通过UserModel去数据库获取到id
#元类自然是为了封装我们之前写的具体的SQL处理函数，从数据库获取数据
#ORM映射基类，通过Model的父类来构造类
class Model(dict,metaclass=ModelMetaclass):
	#这里直接调用了Model的父类dict的初始化方法，把传入的关键字参数存入自身的dict中
	def __init__(self,**kw):
		super(Model,self).__init__(**kw)

	#获取dict的key
	def __getattr__(self,key):
		try:
			return self[key]
		except KeyError:
			raise AttributeError(r"'Model' object has no attribute '%s'"%key)
	def __setattr__(self,key,value):
		self[key] = value
	def getValue(self,key):
		return getattr(self,key,None)
	def getValueOrDefault(self,key):
		value = getattr(self,key,None)
		if value is None:
			field = self.__mappings__[key]
			if field.default is not None:
				value = field.default() if callable(field.default) else field.default
				logging.debug('using default value for %s:%s'%(key,str(value)))
				setattr(self,key,value)
		return value
	#==================往Model类添加类方法，就可以让所有子类调用类方法===========================================

	@classmethod  #这个装饰器是类方法的意思，即可以不创建实例直接调用类方法
	
	async def find(cls,pk):
		''' find object by primary key'''
		rs = await select('%s where `%s`=?'%(cls.__select__,cls.__primary_key__),[pk],1)
		if len(rs) == 0:
			return None
		return cls(**rs[0])
	
	#findAll() --根据WHERE条件查找
	@classmethod	
	async def findAll(cls,where=None,args=None,**kw):
		sql = [cls.__select__]
		if where:
			sql.append('where')
			sql.append(where)
		if args is None:
			args = []
		orderBy = kw.get("orderBy",None)
		if orderBy:
			sql.append("order by")
			sql.append(orderBy)
		limit = kw.get("limit",None)
		if limit is not None:
			sql.append("limit")
			if isinstance(limit,int):
				sql.append("?")
				sql.append(limit)
			if isinstance(limit,tuple) and len(limit) == 2:
				sql.append("?,?")
				args.extend(limit)  #extend() 函数用于在列表末尾一次性追加另一个序列的多个值
			else:
				raise ValueError("错误的limit值:%s"%limit)

		rs = await select(' '.join(sql),args)
		return [cls(**r) for r in rs]
	#findNumber() -- 根据WHERE条件查找，但返回的是整数，适用于select count(*)类型的SQL
	@classmethod
	
	async def findNumber(cls,selectFind,where=None,args=None):
		sql = ['select %s _num_ from `%s`'%(selectFind,cls.__table__)]
		if where:
			sql.append("where")
			sql.append(where)
		rs = await select(" ".join(sql),args,1)
		if len(rs) == 0:
			return None
		return rs[0]['_num_']
	#==========================往Model类型添加实例方法，就可以让所有子类调用实例方法==================================
	#save、update、remove这三个方法需要管理员权限才能操作，所以不定义为类方法，需要创建实例之后才能调用
	
	async def save(self):
		args = list(map(self.getValueOrDefault,self.__fields__))  #将除主键外的属性名添加到args这个列表中
		args.append(self.getValueOrDefault(self.__primary_key__)) #再将主键添加到这个列表的最后
		rows = await execute(self.__insert__,args)
		if rows != 1:
			logging.warn("无法插入记录，受影响的行:%s"%rows)
	
	async def update(self):
		args = list(map(self.getValue,self.__fields__))
		args.append(self.getValue(self.__primary_key__))
		rows = await execute(self.__update__,args)
		if rows != 1:
			logging.wran('failed to update by primary key: affected rows:%s'%rows)
	
	async def remove(self):
		args = [self.getValue(self.__primary_key__)]
		rows = await execute(self.__delete__,args)
		if rows != 1:
			logging.warn('failed to remove by primary key:affected rows:%s'%rows)

