#logging模块定义了一些函数和模块，可以帮助我们对一个应用程序或库实现一个灵活的事件日志处理系统
#logging模块可以记录错误信息，并在错误信息记录完后继续执行
import logging; logging.basicConfig(level=logging.INFO)
#asyncio内置了对异步IO的支持，os模块提供了调用操作系统的接口函数，json模块提供了Python对象到Json模块的转换
import asyncio,os,json,time
from datetime import datetime
#aiohttp是基于asyncio实现的http框架
from aiohttp import web
#Jinja2是仿照Django模板的Python前端引擎模板
#Evironment指的是jinja2模板的配置环境，FileSystemLoader是文件系统加载器，用来加载模板路径
from jinja2 import Environment,FileSystemLoader

import orm
from coroweb import add_routes,add_static

from handlers import cookie2user,COOKIE_NAME

'''
def index(request):
	return web.Response(body=b'<h1>Awesome</h1>',content_type='text/html')
'''
#定义一个初始化jiaja2模板，配置jinja2的环境
def init_jinja2(app,**kw):
	logging.info('init jinja2...')
	#设置解析模板需要用到的环境变量
	options = dict(
		autoescape = kw.get('autoescape',True),  #自动转义xml/html的特殊字符
		#下面两句的意思是{%和%}中间的是python代码而不是html
		block_start_string = kw.get('block_start_string','{%'),#设置代码起始字符串
		block_end_string = kw.get('block_end_string','%}'),#设置代码的终止字符串
		#这两句分别设置了变量的起始和结束字符串
		variable_start_string = kw.get('variable_start_string','{{'),
		variable_end_string = kw.get('variable_end_string','}}'),#{{和}}中间是变量，看过templates目录下的test.html文件后就很好理解了
		auto_reload = kw.get('auto_reload',True)#当模板文件被修改，下次请求加载该模板文件的时候会自动加载修改后的模板文件
	)
	path = kw.get('path',None) #从kw中获取模板路径，如果没有传入这个参数则默认为None
	#如果path为None，则将当前文件所在目录下的templates目录设为模板文件目录
	if path is None:
		#os.path.abspath(__file__)取当前文件的绝对目录
		#os.path.dirname()取绝对目录的路径部分
		#os.path.join(path,name)把目录和名字组合
		path = os.path.join(os.path.dirname(os.path.abspath(__file__)),'templates')
	logging.info('set jinja2 template path:%s'%path)
	#loader=FileSystemLoader(path)指的是到哪个目录下加载模板文件，**options就是前面的options
	env = Environment(loader=FileSystemLoader(path),**options)
	filters = kw.get('filters',None)  #filters=>过滤器
	if filters is not None:
		for name, f in filters.items():
			env.filters[name] = f  #在env中添加过滤器
	app['__templating__'] = env    #前面已经把jinja2的环境配置都复制给env了，这里再把env存入app的dict中，这样app就知道要去哪找模板，怎么解析模板

#这个函数的作用就是当http请求的时候通过logging.info输出请求的信息，其中包括请求的方法和路径
@asyncio.coroutine
def logger_factory(app,handler):
	@asyncio.coroutine
	def logger(request):
		#记录日志
		logging.info('Request:%s %s'%(request.method,request.path))
		#await asyncio.sleep(0.3)
		return (yield from handler(request))
	return logger

@asyncio.coroutine
def auth_factory(app,handler):
	@asyncio.coroutine
	def auth(request):
		logging.info('check user: %s %s'%(request.method,request.path))
		request.__user__ = None    #先把请求__user__属性绑定None
		cookie_str = request.cookies.get(COOKIE_NAME)
		if cookie_str:
			user = yield from cookie2user(cookie_str)
			if user:
				logging.info('set current user:%s'%user.email)
				request.__user__ = user   #将用户信息绑定到请求上
		if request.path.startswith('/manage/') and (request.__user__ is None or not request.__user__.admin):
			return web.HTTPFound('/signin')
		return (yield from handler(request))
	return auth

#只有当请求方法为POST时这个函数才起作用
@asyncio.coroutine
def data_factory(app,handler):
	@asyncio.coroutine
	def parse_data(request):
		if request.method == 'POST':
			if request.content_type.startswith('application/json'):
				request.__data__ = yield from request.json()
				logging.info('request json: %s ' % str(request.__data__))
			elif request.content_type.startswith('application/x-www-form-urlencoded'):
				request.__data__ = yield from request.post()
				logging.info('request from: %s' % str(request.__data__))
		return (yield from handler(request))
	return parse_data


@asyncio.coroutine
def response_factory(app,handler):
	@asyncio.coroutine
	def response(request):
		logging.info('Response handler...')
		r = yield from handler(request)
		#如果结果为StreamResponse,直接返回
		#StreamResponse是aiohttp定义response的基类，即所有响应类型都继承自该类
		#StreamResponse主要为流式数据而设计
		if isinstance(r,web.StreamResponse):
			return r
		#如果响应结果为字节流，则将其为应答的body部分，并设置为流式数据类型
		if isinstance(r,bytes):
			resp = web.Response(body=r)
			resp.content_type = 'application/octet-stream'
			return resp
		#如果响应结果为字符串
		if isinstance(r,str):
			#判断响应结果是否为重定向，如果是，返回重定向后的结果
			if r.startswith('redirect'):
				return web.HTTPFound(r[9:]) #即把r字符串之前的“redirect”去掉
			#然后以utf8对其编码，并设置响应类型为html型
			resp = web.Response(body=r.encode('utf-8'))
			resp.content_type = 'text/html;charset=utf-8'
			return resp
		#如果响应结果为字典，则获取他的jinja2模板信息，此处应为jinja2.env
		if isinstance(r,dict):
			template = r.get('__template__')
			#若不存在对应模板，则将字典调整为json格式返回，并设置响应类型为json
			if template is None:
				resp = web.Response(body=json.dumps(r,ensure_ascii=False,default=lambda o:o.__dict__).encode('utf-8'))
				resp.content_type = 'application/json;charset=utf-8'
				return resp
			else:
				r["__user__"] = request.__user__  #增加__user__，前端页面将依次来决定是否显示评论框
				resp = web.Response(body=app['__templating__'].get_template(template).render(**r).encode('utf-8'))
				resp.content_type = 'text/html;charset=utf-8'
				return resp
		#如果响应结果为整数类型，且在100和600之间,则此时r为状态码，即404,500等
		if isinstance(r,int) and r >= 100 and r < 600:
			return web.Response(r)
		#如果响应结果为长度为2的元组,元组第一个值为整数类型且在100和600之间
		#则t为状态码，m为错误描述，返回状态吗和错误描述
		if isinstance(r,tuple) and len(r) == 2:
			t,m = r
			if isinstance(t,int) and t >= 100 and t < 600:
				return web.Response(t,str(m))
		#默认以字符串形式返回响应结果，并设置类型为普通文本
		resp = web.Response(body=str(r).encode('utf-8'))
		resp.content_type = 'text/plain;charset=utf-8'
		return resp
	#上面6个if其实只用了一个，准确来说只用了半个(响应结果为字典)。
	return response

#定义一个时间过滤器,作用是返回日志创建的时间，用于显示在日志标题下面
def datetime_filter(t):
	delta = int(time.time() - t)
	if delta < 60:
		return u'1分钟前'
	if delta < 3600:
		return u'%s分钟前'%(delta // 60)
	if delta < 86400:
		return u'%s小时前'%(delta // 3600)
	if delta < 604800:
		return u'%s天前' %(delta // 86400)
	dt = datetime.fromtimestamp(t)
	return u'%s年%s月%s日' %(dt.year,dt.month,dt.day)

@asyncio.coroutine
def init(loop):
	#创建数据库连接池
	yield from orm.create_pool(loop=loop,host='127.0.0.1',port=3306,user='www-data',password='www-data',db='awesome')
	#创建app对象，同时传入上文定义的拦截器middlewares
	app = web.Application(loop=loop,middlewares=[
		logger_factory,auth_factory,response_factory
		])

	#初始化jinja2模板，并传入时间过滤器
	init_jinja2(app,filters=dict(datetime=datetime_filter))
	add_routes(app,'handlers')    #自动把handlers模块的所有符合条件的函数注册了
	add_static(app)

	srv = yield from loop.create_server(app.make_handler(),'127.0.0.1',9000)
	logging.info('server start at http://127.0.0.1:9000...')
	return srv

#asyncio的编程模块实际就是一个消息循环。我们asyncio模块中直接获取一个eventloop(时间循环)的引用
#然后把需要执行的协程扔到eventloop中执行，就实现了异步IO
#第一步是获取eventloop

#get_event_loop() => 获取当前脚本下时间循环，返回一个event loop对象(这个对象的类型是"asyncio.windows_event._WindowsSelectorEvent")
loop = asyncio.get_event_loop()
#之后是执行coroutine
loop.run_until_complete(init(loop))
#无限循环运行知道stop()
loop.run_forever()
