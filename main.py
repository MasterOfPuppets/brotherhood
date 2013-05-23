import os
import webapp2
import jinja2
import datetime
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.api import mail
import logging
#helpers
def format_datetime(value, how = 'short'):
	if how == 'short':
		return value.strftime('%Y-%m-%d')
	else:
		return value.strftime('%Y-%m-%d at %H:%m')

def is_next(next_flag):
	if next_flag:
		return 'yes'
	else:
		return ' - - '

def db_key():
	return db.Key.from_path('Brother', 'Version_1')

def BrotherById(idBrother):
	return Brothers.get_by_id(idBrother, parent = db_key())

template_dir = os.path.join(os.path.dirname(__file__),'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir), autoescape = True)
jinja_env.filters['datetime'] = format_datetime
jinja_env.filters['is_next'] = is_next

class Handler(webapp2.RequestHandler):
	def write(self, *a, **kw):
		self.response.out.write(*a, **kw)

	def render_str(self, template, **params):
		t = jinja_env.get_template(template)
		return t.render(params)
	
	def render(self, template, **kw):
		self.write(self.render_str(template, **kw))

	def render_new_brother(self, **params):
		self.render("brother_form.html", vals = params)

	#utility methods
	def update_index(self,brother, index = None):
		"""Updates brother with new index value or creates a new incremented index to the supplied brother"""
		if index:
			new_index = index
		else:
			new_index = Brothers.all().order('-index').get().index #brothers[0].index
			if not new_index:
				new_index = 1
			else:
				new_index = new_index +1
		brother.index = new_index
		brother.put()

	def brotherSetNext(self, b_id):
		getBrother = BrotherById(int(b_id))
		if getBrother:
			self.clearAllNext()
			getBrother.am_i_next = True
			getBrother.put()	
		
	def paramId(self):
		posted_data = self.request.path.split('/')
		return posted_data[-1]
	
	def paramCmd(self):
		posted_data = self.request.path.split('/')
		return posted_data[-2]
	
	def clearAllNext(self):
		b = Brothers.all()
		for brother in b:
			brother.am_i_next = False
			brother.put()
				
	def user_handling(self):
		user = users.get_current_user()
		return user if user else False

class Brothers(db.Model):
	created = db.DateTimeProperty(auto_now_add = True)
	index = db.IntegerProperty()
	name = db.StringProperty(required = True)
	email = db.EmailProperty(required = True)
	g_user = db.UserProperty()
	am_i_next = db.BooleanProperty(default = False)

class LogEntries(db.Model):
	created = db.DateTimeProperty(auto_now_add = True)
	name = db.StringProperty(required = True)
	email = db.EmailProperty(required = True)
	b_id = db.ReferenceProperty()
	waiting_days = db.IntegerProperty(default = 0)

class MainPage(Handler):
	def get(self):
		
#		for i in range(1,12):
#			b = Brothers(parent = db_key(),name = "Look at my Brother's name %d"%(i), email = "thisis@Mail %d"%(i))
#			b.am_i_next = False
#			b.index = i
#			b.put()
		brothersLst = Brothers.all().order('index')
		user = self.user_handling()
		past = LogEntries.all().order('-created')
		self.render("main_page.html",brothers = brothersLst, entries = past, user = user, users = users)

class Admin(Handler):
	def get(self):
		user = self.user_handling()
		if not user:
			self.redirect("/")
			return
		logging.info("User-id: %s" % user.user_id())
		if not user.user_id() in ['102749944644647152798']:
			self.redirect("/")
			return			
		self.render("main_admin.html", user = user, users = users)

class AdminList(Handler):
	def get(self):
		lst = Brothers.all().order('index')
		limits = []
		if lst.count() > 0:
			limits.append(lst[0].index);
			limits.append(lst[lst.count() -1])
		user = self.user_handling()
		self.render("admin_list.html", brothers = lst, limits = limits,user = user, users = users)		
	

class Wipe(Handler):
	def post(self): # it comes from an ajax request
		#get the brother index
		brother_to_delete = BrotherById(int(self.paramId()))
		if brother_to_delete:
			index_to_keep = brother_to_delete.index
			#delete the bastard
			brother_to_delete.delete() 
			#update the indexes of the other brothers, Handler
			brothers_to_update = Brothers.all().filter('index >', index_to_keep).order('index')
			for b in brothers_to_update:
				b.index = index_to_keep
				b.put()
				index_to_keep += 1
		
class SetNext(Handler):
	def get(self):
		brother_id = self.paramId()
		self.brotherSetNext(brother_id)
		self.redirect("/admin-the-list")
			
class BrotherDone(Handler):
	def	get(self):
		try:
			getBrother = BrotherById(int(self.paramId()))
		except:
			self.redirect("/admin-the-list")
			return
		if not getBrother:
			self.redirect("/admin-the-list")
			return
		bq = db.GqlQuery("select * from Brothers where index > :1 order by index limit 1", getBrother.index)
		newBrother = bq.get()
		if not newBrother: # we have reached the end of the list
			t = Brothers.all().filter('index = ', 1)
			newBrother = t[0]
		self.brotherSetNext(newBrother.key().id())
		lastEntry = LogEntries.all().order("-created")
		daysElapsed = 0
		cnt = lastEntry.count()
		#print cnt
		if cnt > 0:
			delta =  datetime.datetime.now() - lastEntry[0].created
			daysElapsed = int(delta.total_seconds() / 86400)
		else:
			daysElapsed = 0
		l = LogEntries(name = getBrother.name, email = getBrother.email,b_id = getBrother.key(), waiting_days = daysElapsed )
		l.put()
		email = EmailBrothers()
		email.send("The list was updated", """Dear brothers, the list was updated.
%s brought the package today.
Next up is %s.

May the natao live forever!
http://big-natao.appspot.com
		""" % (getBrother.name, newBrother.name))
		self.redirect("/admin-the-list")	
								
class ChangeIndex(Handler):
	def get(self):
		actual_index = 0
		new_index = 0
		change_direction = 0 # -1 Up, 1 Down
		try:
			getBrother = BrotherById(int(self.paramId()))
			change_direction = -1 if self.paramCmd() == 'index_up' else 1
		except:
			self.redirect("/admin-the-list")
			return
		if getBrother:
			try:
				#get the index and update it of the actual brother
				actual_index = getBrother.index
				new_index = actual_index + (change_direction)
				#get the brother whose index is going to be swapped
				brotherToChange = Brothers.all().filter('index',new_index).get()			
			except:
				self.redirect("/admin-the-list")
				return
			#update both brothers id possible
			if  brotherToChange:
				self.update_index(getBrother,new_index)
				self.update_index(brotherToChange, actual_index)
		else:
			self.redirect("/admin-the-list")
		self.redirect("/admin-the-list")

class NewBrother(Handler):	
	def get(self):
		user = self.user_handling()
		if not user:
			self.redirect("/")
			return 		
		error_name = ""
		error_email = ""
		name = ""
		email = ""
		self.render("brother_form.html",name = name , email = email, error_name = error_name, error_email = error_email, user = user, users = users )

	def post(self):
		name = self.request.get('name')
		email = self.request.get('email')
		error_name = ""
		error_email = ""
		user = self.user_handling()
		if name and email:	

			#save the record
			newBrother = Brothers(parent = db_key(), name = name, email = email)
			newBrother.put()
			self.update_index(newBrother)
			self.redirect("/")
		else:
			# we have an input error
			if not name:
				error_name = "Please input brother's name"
			if not email:
				error_email = "Brother's email is mandatory"
		self.render("brother_form.html",name = name , email = email, error_name = error_name, error_email = error_email , user = user, users = users)

class EmailBrothers():
	def send(self, subject, msg):
		lSender = "Brotherhood of the big natao <uniko@iol.pt>"
		brothers = Brothers.all()
		brothersList = []
		for brother in brothers:
			brothersList.append(brother.email)
			
		mail.send_mail(sender = lSender,
		              to = brothersList,
		              subject = subject,
		              body= msg)
			
app = webapp2.WSGIApplication([('/', MainPage),
				('/admin-the-list',Admin),
				('/index_up/.*',ChangeIndex),
				('/index_dw/.*',ChangeIndex),
				('/newbrother',NewBrother),
				('/setnext/.*',SetNext),
				('/wipe/.*',Wipe),
				('/admin-list',AdminList),
				('/brother-done/.*',BrotherDone)],
                              debug=True)




