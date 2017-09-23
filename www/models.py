import time
#uuid 是python 中生成唯一ID的库
import uuid 
from orm import Model,StringField,BooleanField,FloatField,TextField

def next_id():
	#time.time()返回当前时间的时间戳
	#uuid4()是由伪随机数得到，有一定的重复概率，该概率可以计算出来
	return "%015d%s000"%(int(time.time()*1000),uuid.uuid4().hex)

#这是一个用户名的表
class User(Model):
	__table__ = 'users'

	id = StringField(primary_key=True,default=next_id,ddl='varchar(50)')
	email = StringField(ddl='varchar(50)')
	passwd = StringField(ddl='varchar(50)')
	admin = BooleanField()
	name = StringField(ddl='varchar(50)')
	image = StringField(ddl='varchar(500)')
	created_at = FloatField(default=time.time)       #创建时间的缺省值是函数time.time，设置为当前日期和时间

#这是一个博客表
class Blog(Model):
	"""docstring for Blog"""
	__table__ = 'blogs'

	id = StringField(primary_key=True,default=next_id,ddl='varchar(50)')
	# email = StringField(ddl='varchar(50)')
	# password = StringField(ddl='varchar(50)')
	# admin = BooleanField()
	user_id = StringField(ddl='varchar(50)')
	user_name = StringField(ddl='varchar(50)')
	user_image = StringField(ddl='varchar(500)')
	name = StringField(ddl='varchar(50)')
	summary = StringField(ddl='varchar(200)')
	content = TextField()
	created_at = FloatField(default=time.time) 

#这是一个评论的表
class Comment(Model):
	__table__ = 'comments'

	id = StringField(primary_key=True,default=next_id)
	blog_id = StringField(ddl='varchar(50)') #博客id
	user_id = StringField(ddl='varchar(50)')  #评论者id
	user_name = StringField(ddl='varchar(50)')  #评论者名字
	user_image = StringField(ddl='varchar(500)') #评论者上传的图片
	content = TextField()
	created_at = FloatField(default=time.time)
