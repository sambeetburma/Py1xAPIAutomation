#!l:\py1xapiautomation\venv\scripts\python.exe

MajVer = 7      # The integral part is the document structure version
MinVer = 1

DateVer = 'Mar 2008'

# wb.py  CGI based billboard management
#
# This CGI script is an utility to manage a web based
# billboard where documents can be posted and edited by authorized users. 
# Documents can have an expiration date and can thus be removed (by running 
# this same program) when expired.
#
# Note: if the program is run with name: wt.py, debug mode is enabled by default

#####################################################################
# Start main customization section. The following variables MUST be 
# modified according to your configuration 

root_http   = '/BillBoards'            # This is relative to server's root
root_dir    = '/opt/HTDOCS/BillBoards' # Actual filepath to billboard dir

#root_http   = '/wb'                        # This is relative to server's root
#root_dir    = '/var/www/html/wb'           # Actual filepath to billboard dir
domain      = 'arcetri.astro.it'           # e-mail domain
smtphost    = 'hercules.arcetri.astro.it'  # smtp host
def_lang    = 'us'                         # The vocabulary file "voc.ini" is 
                                           # got from directory '_lang_us'

# The following variables are suitable defaults, but you may want to
# modify them for some special need

debug       = True       # Set to True for debug output
def_ttl     = 18000      # Session expiring time (five hours)
do_log      = True       # Set to False to avoid log recording
log_size    = 500000     # Max size of log files
log_number  = 4          # Number of preserved copies of log files 
                         # when rotating
#auth_mode   = 'local'
auth_mode   = 'shadow'   # Method for user authentication. 
                         #   local: check with WB specific mechanism
                         #   unix: check with unix /etc/passwd
                         #   shadow: check against /etc/shadow
                         #   nis: check against NIS passwd
                         # Using any selection other then local the selected
                         # method is used and then local is also attempted, if
                         # no match is found.
                         # Local password file is managed by the wb.py utility
                         # executing it from command line

#####################################################################


root_users = ('admin','root','administrator')  # Users accepted for global operations
                                               # (Billboard creation/delete)

accepted_types = ('.pdf','.html','.htm','.txt','.jpg','.gif',  # Accepted attachment filetypes
                  '.png','.ps'                               )

                       ####### Some colors  ############################
adm_color = '#ffaaaa'  # color for Administrative commands (see op_list)
box_color = '#5555ff'  # Background for logos
op_color  = '#ccccff'  # Bacground for operation header
                       #################################################
import cgi
import sys,os
import fcntl
import re
import types
import string
import cPickle as pickle
import time,random

Version = '%d.%d' % (MajVer,MinVer)
ident = 'wb.py - L.Fini (lfini@arcetri.inaf.it). Version %s, %s' %(Version,DateVer)
logger=None
cgimode=0

action=''
cur_lang='-'
rem_addr='LOCAL'
user='None'
 
pwname= os.path.join('_var','wb.users')
lang_file='voc.ini'


                       # Default notification message for new document
mailnew=(
'************************************************************************',
'A new document has been posted in billboard: %(BBOARD)s',
'',
'%(TITLE)s',
'',
'See: %(HREF)s',
'************************************************************************',
)

                          # Default notification message for updated document
mailupd=(
'************************************************************************',
'The following document has been updated in billboard: %(BBOARD)s',
'',
'%(TITLE)s',
'',
'See: %(HREF)s',
'************************************************************************',
)

                                               # Default initialization data
InitData = { 'allowed_users' : ['everybody'], 
             'index_header'  : ['<h3>Documents in billboard: <i>%(BBOARD)s</i></h3>',
                                '%(SEARCH)s<p><blockquote><ul>'],
             'index_item'    : ['<p><li> %(DATE)s &nbsp;&nbsp;&nbsp;%(EXPIR)s',
                                '<br><a href=%(HREF)s>%(TITLE)s</a>'],
             'index_item_exp': ['<p><li> %(DATE)s &nbsp;&nbsp;&nbsp;%(EXPIR)s <font color=red> Expired!</font>',
                                '<br><a href=%(HREF)s>%(TITLE)s</a>'],
             'index_footer'  : ['</ul></blockquote>'],
             'index_src'     : '%(N_ITEMS)s found',
             'doc_header'    : ['%(DATE)s %(EXPIR)s',
                                '<h3>%(TITLE)s</h3> %(AUTHOR)s<p>'],
             'doc_footer'    : [],
             'sort_order'    : 'date ascending',
             'author_fmt'    : 'By: %s',
             'noauthor_fmt'  : '',
             'mail_to'       : [],
             'mail_from'     : 'WBmaster@localdomain',
             'show_future'   : True,         # Show documents with date in the future
             'search_fmt'    : 'Search: %s', # Search field format (see wb.ini)
             'expir_fmt'     : '(Expiration: %s)',
             'noexpir_fmt'   : '(No expiration)',
             'mail_new'      : mailnew,       # A long string: see above
             'mail_update'   : mailupd,       # A long string: see above
             'date_mode'     : 0,            # (0: numeric, 1: months as words)
             'language'      : def_lang,
             'expir_required': False,
             'author_req'    : True,
             'delete_expired': False,        # If false expired files are not deleted but moved
                                             # to the "deleted" directory

}

COMMASPACE = ', '
NBSP15 = '&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;'
NBSP10 = '&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;'
NBSP5 = '&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;'

voc = { 'ERROR': 'Error', 'REPORT':'Report error to the sysmgr', }

InitData['from_file']=''

#### Class for attachment management
class Attachment:
  def __init__(self,title,orig_name,local_name,id):
    self.title=title
    self.orig_name=orig_name
    self.local_name=local_name
    self.id=id

#### Class for documents
class Document:
  def __init__(self):
    self.attachments=[]
    self.max_id=0
    self.date=Date()
    self.expir=Date(0)
    self.st_sequence=0    # index of posting
    self.expir_required=InitData['expir_required']
    self.version=MajVer
    self.st_sid  = 'DOC-%x'%int(time.time()*10)
    self.st_style = 'TA'
    self.st_url   = ''
    self.st_title=''
    self.st_author=''
    self.st_text=''
    self.st_html=''


############################################################################################
  def repr(self,bboard,http_path):
    items={'BBOARD': bboard, 'DATE': self.date, 'TITLE': self.st_title }
    if self.st_author:       # Include author specification only if an author is specified
      items['AUTHOR'] = InitData['author_fmt'] % self.st_author
    else:
      items['AUTHOR'] = InitData['noauthor_fmt']

    items['EXPIR']=expir_str(self.expir)
    items['SEQNUM'] = '%d' % self.st_sequence

    ret = '<!--    Begin document preview   -->\n' 
    if self.st_style == 'TA':
      ret += '\n'.join(InitData['doc_header']) % items
      if not self.st_html: 
        p1='<pre>'; p2='</pre>'
      else:
        p1=''; p2=''

      ret +=  p1+self.st_text+p2 + '\n'
                                    # Process attachments
      if self.attachments:
        ret += '    <!--  Begin attachment list -->\n'
        ret +=  '<hr><ul>\n'
        natc=len(self.attachments)
        for k in range(0,natc):
          ret +=  '<li><a href=%s/%s>%s</a>\n' % (http_path,self.attachments[k].local_name,self.attachments[k].title)
        ret +=  '</ul>\n'
        ret += '    <!--  End attachment list   -->\n'
      ret += '\n'.join(InitData['doc_footer']) % items

    if self.st_style == 'AO':     # Preview output for "Attachment only" style
      pass

    if self.st_style == 'LO':     # Preview output for "Link only" style
      pass

    ret += '<!--    End document preview     -->\n'
    return ret

  def update(self):     # Updates Document structure to current version
    ver=getattr(self,'version',1)
    self.new=getattr(self,'new',0)
    self.expir_required=getattr(self,'expir_required',0)
    self.st_author=getattr(self,'st_author','')
    self.st_style = getattr(self,'st_style','TA')
    self.st_url = getattr(self,'st_url','')
    self.st_sequence=getattr(self,'st_sequence',0)

    if ver < 4:
      if self.expir.time>0:
        self.expir=Date(self.expir.time)
      else:
        self.expir=Date(0)
      self.date=Date(self.date.time)

    self.version=MajVer


###################################################################################
def printinit(cgimode,updt={}):       # Print initialization data (debug support)
  if cgimode:
    
    if InitData['from_file']:
      print '<h3>Initialization data [from file: %s]</h3>' % InitData['from_file']
    else:
      print '<h3>Initialization data [default]</h3>'
    fmt1= "<pre>"
    fmt2= '<b>%s</b> [%s]: %s'
    safef = lambda x: cgi.escape(repr(x))
    fmt3 = "</pre>"
  else:
    fmt1= ""
    fmt2= '%s [%s]: %s'
    safef = lambda x: x
    fmt3 = ""
  print fmt1
  ks=InitData.keys()
  ks.sort()
  iii = updt.keys()
  for k in ks:
    if  k in  iii:
       src='init file'
    else:
       src='default'
    print fmt2% (k,src,safef(InitData[k]))
  print fmt3

############################################################################################
def expir_str(spec):
  if spec:
    ret = InitData['expir_fmt'] % spec
  else:
    ret = InitData['noexpir_fmt']
  return ret

#############################################################################
def err_exit(msg,type=1):          # Output an error message
  if cgimode:
    print '<h3>%(ERROR)s:' % voc
    print '<font color="red"> %s</font></h3>' % msg
    if type: print '<h3>%(REPORT)s</h3>' % voc
    footer()
  else:
    print 'Error: %s' % msg,
    if type: 
      print '[system error]'
    else:
      print
  sys.exit()

#############################################################################################
def set_lang(lang=''):         # NB: messages in this routine cannot be made in other 
                            #     languages, because vocabulary is not yet available
  global voc,cur_lang,help_path

  if not lang: lang=def_lang

  if lang != cur_lang:
    newvoc={}
    lang_dir = '_lang_'+lang
    lfile=os.path.join(root_dir,lang_dir,lang_file)
    if debug:
       print "<h3>Requested language file: %s" % lfile

    if not os.path.exists(lfile):
      lang_dir = '_lang_'+def_lang
      lfile=os.path.join(root_dir,lang_dir,lang_file)
      if debug:
         print "<h3>Requested language file not found, trying: %s" % lfile

    try:
      execfile(lfile,{},newvoc)
    except:
      msg = '[%s] reading language file: %s'%(sys.exc_type,lfile)
      err_exit(msg)
    else:
      voc=newvoc
      cur_lang=lang

    help_path=root_http + '/' + lang_dir

################################################################################
def initfile(arc_dir):           # Read initialization file (wb.ini)
                                 # merges definitions in InitData and
                                 # in vocabulary
  global voc

  initname = os.path.join(arc_dir,'wb.ini')
  if not os.path.exists(initname): 
    return
    
  it={}
  try:
    execfile(initname,{},it)
  except:                    # no init file, use defaults
    err_exit('Error [%s] reading initialization file: %s'%(sys.exc_type,initname))
    return

  InitData.update(it)
  set_lang(InitData['language'])   # Redefine vocabulary (if needed)
  InitData['from_file']=initname

  if(debug): 
    printinit(cgimode,updt=it)

def docload(fname):  # Uses pickle.load() to load a document, checking
                     # proper document format
  fd=open(fname)
  doc=pickle.load(fd)
  fd.close()
  if doc.version != MajVer: 
    doc.update()
  return doc



################################################################################
################################################################################
################################################################################
# Class: Date  - manipulate dates (dd/mm/yy)
class Date:
  sep=re.compile('[^0-9]+')

  def __init__(self,datespec=None,mode=0):
    self.mode=mode
    self.date=[0,0,0,0,0,0]
    self.set(datespec)

  def set(self,datespec):             # set date. Both numerical (a time.time() value)
                                      # and string (dd/mm/yy) specification are allowed.
                                      # if datespec is None, current date is set
    if type(datespec) is str:
      self.__setstr(datespec)
    elif type(datespec) is int:
      self.__setint(datespec)
    else:
      self.__setint(int(time.time()))

  def defined(self):                # Returns True if the date is defined
    return self.date[0]>0

  def expired(self,tm=None):            # Returns: true if the date is prior than specified
                                        # time. If no time is given, uses current time
    if self.date[0]==0: return False    # If date is undefined, return 1
    if not tm:
      tm=time.time()

    ymd = time.localtime(tm)[0:3]
    if ymd[0]<self.date[0]: return  False
    if ymd[0]>self.date[0]: return  True
    if ymd[1]<self.date[1]: return  False
    if ymd[1]>self.date[1]: return  True
    if ymd[2]<self.date[2]: return  False
    if ymd[2]>self.date[2]: return  True
    return False
 
  def cmp(self,comp):          # Retuns -1, 0, 1 if Date is prior,same,later
                               # than argument
    if self.date[0]<comp.date[0]: return -1
    if self.date[0]>comp.date[0]: return  1
    if self.date[1]<comp.date[1]: return -1
    if self.date[1]>comp.date[1]: return  1
    if self.date[2]<comp.date[2]: return -1
    if self.date[2]>comp.date[2]: return  1
    return 0

  def setmode(self,mode):             # Change date display mode 0: numerical month
                                      #                          1: word month
    self.mode=mode

  def __setstr(self,str):
      dd=map(int,Date.sep.split(str)[0:3])
      dd.reverse()
      dd.extend([12,0,0])
      self.date=dd             # [year,month,day,hour,minute,sec]

  def __setint(self,val):
    if val==0: return
    self.date=time.localtime(val)[0:6]

  def __repr__(self): 
   if self.date[0]==0: return ''
   if self.mode==0:
     return '%2.2d/%2.2d/%4.4d' % (self.date[2],self.date[1],self.date[0])
   else:
     return '%2.2d %s %4.4d' % (self.date[2],
                                voc['MONTHS'][self.date[1]-1],
                                self.date[0])

  def __str__(self): return self.__repr__()




#############################################################################################
def environ():        # prints environment status (for debug support)
  env=os.environ
  print '<hr>'
  print '<h3>     UID: %s </h3>'%os.getuid()
  print '<h3>sys.argv: %s </h3>'%sys.argv
  print '<h3>basename: %s </h3>'%os.path.basename(sys.argv[0])
  print "<h3>Environment variables</h3>"
  print '<pre>'
  ks=env.keys()
  ks.sort()
  for k in ks:
    print "<b>%s</b>: %s" % (k,env[k])
  print '</pre>'

  print '<h3>Customization parameters:</h3>'
  print '<pre>'
  print '<b>root_http:</b>', root_http
  print '<b>root_dir:</b>', root_dir
  print '<b>domain:</b>', domain
  print '<b>smtphost:</b>', smtphost
  print '<b>debug:</b>', debug
  print '<b>def_ttl:</b>', def_ttl
  print '<b>def_lang:</b>', def_lang
  print '<b>do_log:</b>', do_log
  print '<b>log_size:</b>', log_size
  print '<b>log_number:</b>', log_number
  print '</pre>'

def show_input(action,form,args):      # Printout arguments and input from form
  print '<h3>Relevant input</h3>'
  print '<pre>'
  print '<b>action:</b>',action
  print '<b>URL args:</b>', cgi.escape(','.join(args))
  print '</pre>'

  if form:
    print '<h3>Data from form:</h3>'
    print '<pre>'
    for k in form.keys():
      val=form[k]
      if getattr(val,'filename',None):
        print '<b>%s [filename: %s]</b>' % (k,cgi.escape(val.filename))
      else:
        val=form.getlist(k)
        print '<b>%s</b>: %s' % (k,cgi.escape(','.join(val)))
    print '</pre>'
  else:
    print '<h3>No form data</h3>'


def show_globals():      # Printout relevant global variables
  global action,mgmtact,cgimode,rem_addr,user,voc,http_path,help_path,root_dir,cur_lang

  print '<h3>Relevant global variables:</h3>'
  g=globals()
  print '<pre>'
  if g.has_key('action'):    print '<b>   action:</b>', action
  if g.has_key('cur_lang'):  print '<b> cur_lang:</b>', cur_lang
  if g.has_key('help_path'): print '<b>help_path:</b>', help_path
  if g.has_key('http_path'): print '<b>http_path:</b>', http_path
  if g.has_key('mgmtact'):   print '<b>  mgmtact:</b>', mgmtact
  if g.has_key('rem_addr'):  print '<b> rem_addr:</b>', rem_addr
  if g.has_key('root_dir'):  print '<b> root_dir:</b>', root_dir
  if g.has_key('user'):      print '<b>     user:</b>', user
  print '</pre>'

#############################################################################################
def show_document(bboard,document,root_dir,http_path):   # Shows the given document
  fpath=os.path.join(root_dir,bboard,document)
  doc=docload(fpath)
  print doc.repr(bboard,http_path)
  print '</body>\n</html>'

#############################################################################################
def search_form(act,bb, sfmt):
  if not sfmt: 
    return ''
  else:
    return '<form method="post" action="%s">\n' % act + \
           '<input type=hidden name=st_bboard value="%s">\n' %bb + \
           sfmt % '<input type=text name="do_search">' + '</form>'

#############################################################################################
def show_index(arc_dir,what=''):        # Shows an index of documents in given bboard
                                        # a document list may be provided by caller
  arc_name=os.path.basename(arc_dir)

  docl=document_list(arc_dir,InitData['sort_order'],what)
  items={'BBOARD': arc_name, 
         'N_ITEMS': str(len(docl)),
         'SEARCH': search_form(action,arc_name,InitData['search_fmt']),
         'STRING': what }
  print  '\n'.join(InitData['index_header']) % items
  if what: print InitData['index_src'] % items
  print '<!-- Begin index list  -->'
  for doc in docl:
    if doc['st_author']:       # Include author specification only if an author is specified
      items['AUTHOR'] = InitData['author_fmt'] % doc['st_author']
    else:
      items['AUTHOR'] = InitData['noauthor_fmt']
    if doc['st_style'] == 'TA':
      items['HREF']='"%s?cmd=show&bb=%s&doc=%s"' % (action,arc_name,doc['st_sid'])
    elif doc['st_style'] == 'AO':
      items['HREF']='"%s/%s"' % (http_path,doc['first_atch'])
    else :
      items['HREF']=doc['st_url']
    
    items['SEQNUM']='%d' % doc['st_sequence']
    items['DATE']=doc['date']
    items['TITLE']=doc['st_title']
    items['EXPIR'] = expir_str(doc['expir'])
    if doc['expir'].expired():
      index_fmt = '\n'.join(InitData['index_item_exp'])
    else:
      index_fmt =  '\n'.join(InitData['index_item'])
    if index_fmt: print  index_fmt % items

  print '<!-- End index list    -->'
  print '\n'.join(InitData['index_footer']) % items
  print '</body>\n</html>'

#############################################################################################
def selectsort(order):   # Selects a sort method for a list of documents
  num=0
  if order.find('expir')>=0: 
    field='expir'
  elif order.find('date')>=0:
    field='date'
  else:
    field='st_sequence'
    num=1

  if order.find('desc')>=0:
    if num:
      return lambda a,b: b[field]-a[field]
    else:
      return lambda a,b: b[field].cmp(a[field])
  else:
    if num:
      return lambda a,b: a[field]-b[field]
    else:
      return lambda a,b: a[field].cmp(b[field])

#############################################################################################
def document_list(arc_dir,order='',ss=None):   # Generates a list of document in given bboard
  docs=filter(lambda x: x[0:4]=='DOC-', os.listdir(arc_dir))
  docl=[]
  if ss: mtc=re.compile(ss,re.I)
  for n in docs:
    fpath=os.path.join(arc_dir,n)
    doc=docload(fpath)
    if ss:
      if not mtc.search(doc.st_text): continue
    if doc.attachments:
      first_atch = doc.attachments[0].local_name
    else:
      first_atch = ''
    docl.append({'date'        : doc.date,
                 'expir'       : doc.expir,
                 'st_sequence' : doc.st_sequence,
                 'first_atch'  : first_atch,
                 'st_title'    : doc.st_title,
                 'st_author'   : doc.st_author,
                 'st_style'    : doc.st_style,
                 'st_url'      : doc.st_url,
                 'st_sid'     : doc.st_sid})

  if order:
    sortfunc=selectsort(order)
    docl.sort( sortfunc )
  return docl

#############################################################################################
def op_header(txt):       # Returns a properly formatted header for all operation pages
  ret  = '<table width="100%" cellpadding=5><tr>\n' 
  ret += '<td bgcolor="%s" width=45><a href=%s/about.html>\n' % (box_color,help_path)
  ret += '<img src=%s/_img/wb.png alt="%s"></a></td>\n' % (root_http,voc['ALT1']) 
  ret += '<td bgcolor="%s"><h3>'%op_color +NBSP10+'%s</h3></td>\n' % txt
  ret += '<td bgcolor="%s" width=45><a href=%s/help.html>\n' % (box_color,help_path)
  ret += '<img src=%s/_img/qm.png alt="%s"></a></td>\n' % (root_http,voc['ALT2']) 
  ret += '</tr></table>\n'
  return ret

#############################################################################################
def op_list(bb,act,mgmtact):                     # returns a properly formatted line for a 
                                                 # list of billboard operations
  ret  = '<tr><td> <a href="%s?cmd=list&bb=%s">%s</a></td>' % (act,bb,bb)
  ret += '<td> [<a href="%s?bb=%s&cmd=edit">%s</a>]'          % (mgmtact,bb,voc['MODIF'].replace(' ','&nbsp;'))
  ret += ' &nbsp;[<a href="%s?bb=%s&cmd=new">%s</a>]'           % (mgmtact,bb,voc['NEWDOC'].replace(' ','&nbsp;'))
  ret += ' &nbsp;[<a href="%s?bb=%s&cmd=clean">%s</a>]'         % (mgmtact,bb,voc['MAINTN'].replace(' ','&nbsp;'))
  ret += ' &nbsp;[<a href="%s?bb=%s&cmd=info">%s</a>]</td>'          % (mgmtact,bb,voc['INFO'].replace(' ','&nbsp;'))
  ret += '<td bgcolor="%s"> [<a href="%s?bb=%s&cmd=editini">%s</a>]' % (adm_color,mgmtact,bb,voc['EDITINI'].replace(' ','&nbsp;'))
  ret += ' &nbsp;[<a href="%s?bb=%s&cmd=rembb">%s</a>]</td></tr>'   % (mgmtact,bb,voc['REMBB'].replace(' ','&nbsp;'))
  return ret

#############################################################################################
def dirlist(root_dir):                 # Returns a list of directories
  try:
    files=os.listdir(root_dir)
  except:
    err_exit('%(READDIR)s: '%voc + root_dir)

  list=[]
  for f in files: 
    if f[0] == '.' or f[0]=='_': continue          # Ignore hidden directories
    fn=os.path.join(root_dir,f)
    if os.path.isdir(fn): list.append(f)

  list.sort()
  return list

#############################################################################################
def bboard_list(root_dir):             # Print list of billboards, properly formatted in HTML
  global voc

  print '<!-- Generated by bboard_list() [wb] -->'
  print op_header(voc['BBLIST'])
  
  list=dirlist(root_dir)
  if list:
    print '<blockquote><table border=1 cellpadding=5>'
    print '<tr><th> %s </th><th> %s </th><th bgcolor="%s"><img src=%s/_img/admin.png> %s </th></tr>' %   \
                                (voc['NAME'],voc['USEROPS'],adm_color,root_http,voc['ADMINOPS'])
    for f in list: 
      if f[0]=='_': continue
      if f[0]=='.': continue
      print op_list(f,action,mgmtact)
    print '</table></blockquote><hr>'

  print '<blockquote><h4><ul>'
  print '<li> <a href=%s?cmd=newbb>%s</a></ul></h4>' % (mgmtact,voc['BBCREA'])
  print '<ul><li> <a href=%s?cmd=log>%s</a>' % (mgmtact,voc['VIEWLOG'])
  print '<li> <a href=%s?cmd=voc>%s</a>' % (mgmtact,voc['VIEWVOC'])
  print '</ul></blockquote>'
  footer()


def header():
  print "Content-Type: text/html\n"     # HTML is following
  print '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">'
  print '<html>\n<head>'
  print '<meta name="generator" content="%s">' % ident
  print '<link rel="icon" href="%s/_img/wb.ico" type="image/x-icon">' % root_http
  print '</head>\n<body>'


#############################################################################################
def footer(act=''):           # Prints HTML document footer (for management functions)

  if act: 
    print '<h4><a href="%s">'% act
    print '%(BACKTOLIST)s</a></h4>'% voc
  print '<hr><font size=1><center>Powered by: %s</center></font>' % ident
  print '</body>\n</html>'

#############################################################################################
def run_cgi():           # This part runs when invoked by the Apache http server
  global action,mgmtact,cgimode,rem_addr,user,voc,http_path,help_path,root_dir

  cgimode=1        

  header()

  if debug: 
    import cgitb; cgitb.enable()        # enable debug HTML output

  method = os.environ['REQUEST_METHOD']
  rem_addr=os.environ['REMOTE_ADDR']    # Extract "action" from input data
  request = os.environ['REQUEST_URI'].split('?')
  action = request[0]
  aux=action.split('.')
  mgmtact=action[:-3]+'mgmt.py'
  form=cgi.FieldStorage()

  if len(request)>1:
    args=request[1].split('&') # Extract input arguments
  else:
    args=[]

  indata={}
  for a in args:
    if '=' in a:
      k,v = a.split('=')
      indata[k]=v
    else:
      indata['bb']=a

  lang = indata.get('lang')
  set_lang(lang)    # set default vocabulary

  if debug: 
    environ()                           # Printout environment
    show_input(action,form,args)
    show_globals()

  if method == 'GET': # Request method is GET: session begins here

    cmd = indata.get('cmd')
    bboard=indata.get('bb')
    if not cmd:
      if not bboard:
        bboard_list(root_dir)           # show bboard list
        sys.exit()                      # and return
      else:
        cmd='list'
    
    if not bboard:
      err_exit('SYSTEM',1)

    arc_dir=os.path.join(root_dir,bboard)   # get bboard directory path
    if not os.path.exists(arc_dir): 
      err_exit('%s: %s'% (voc['BBNOTEXS'], arc_dir))

    http_path='/'.join([root_http,bboard])

    initfile(arc_dir)

    if cmd == 'show':
      doc=indata.get('doc')
      if not doc:
        err_exit('SYSTEM',1)
      show_document(bboard,doc,root_dir,http_path)
    elif cmd == 'list':
      show_index(arc_dir)
    else:
      err_exit('SYSTEM',1)
    
    sys.exit()

########################################################################################
                                  # We get here only for request method == POST 
                                  # i.e.: it is a search request
  bboard=form.getfirst('st_bboard')
  arc_dir=os.path.join(root_dir,bboard)
  http_path=os.path.join(root_http,bboard)
  initfile(arc_dir) 

  if 'do_search' in form:        # This is a search request
    show_index(arc_dir,form.getfirst('do_search'))
    sys.exit()

  err_exit('Illegal command',1)



#############################################################################################
def show_file(bboard,document):
  fpath=os.path.join(bboard,document)
  a=docload(fpath)

  for k in dir(a):
    attr=getattr(a,k)
    if not callable(attr):
      print "document.%s: "%k, attr

#############################################################################################
def pwrite(pwfile,users):
  import stat

  try:
    fd=open(pwfile,'w')
  except:
    print voc['PWFILERR'] + pwfile
    return 0

  keys = users.keys()
  keys.sort()
  print >>fd,'# password file generated on',time.asctime()
  for k in keys:
    print >>fd,'%s = "%s"' % (k,users[k])
  print >>fd,'# end'
    
  fd.close()
                                              # The password file must be owned by root
                                              # and readable by others
  os.chmod(pwfile,stat.S_IRUSR+stat.S_IWUSR+stat.S_IRGRP+stat.S_IROTH)
  return 1
  
def add_user(userid,passwd):
  import sha

  pwfile =  os.path.join(root_dir,pwname)
  users={}
  print 'reading local password file: "%s"' % pwfile
  try:
    execfile(pwfile,{},users)
  except:                    # No password file: it will be created
    print 'No password file. Creating it'

  a=sha.new(userid)
  a.update(passwd)
  users[userid]=a.hexdigest()

  if pwrite(pwfile,users): 
    print 'Added user: %s' % userid

#############################################################################################
def rm_user(userid):
  import stat

  pwfile =  os.path.join(root_dir,pwname)
  users={}
  print 'reading local password file: "%s"' % pwfile
  try:
    execfile(pwfile,{},users)
  except:                    # No password file: it will be created
    print 'No password file.'
    return

  if userid in users:
    del users[userid]
    print 'User %s removed' % userid
    pwrite(pwfile,users)
  else:
    print 'No user %s' % userid

#############################################################################################
def list_users():
  pwfile =  os.path.join(root_dir,pwname)
  users={}
  print 'Reading local password file: "%s"' % pwfile
  try:
    execfile(pwfile,{},users)
  except:                    # No password file: it will be created
    print 'No password file.'
    return
  keys = users.keys()
  keys.sort()
  print 
  for k in keys:
    print '%s' % k
  print
  
  
#############################################################################################
def run_standalone():

  global cgimode,action,rem_addr,root_dir

  cgimode=0        

  rem_addr='LOCAL'

  if len(sys.argv) < 2: helpexit()

  if sys.argv[1] == '-s':
    if len(sys.argv) < 4: helpexit()
    show_file(sys.argv[2],sys.argv[3])

  elif sys.argv[1] == '-u':
    set_lang()
    if len(sys.argv) < 4: helpexit()
    add_user(sys.argv[2],sys.argv[3])
  elif sys.argv[1] == '-r':
    set_lang()
    if len(sys.argv) < 3: helpexit()
    rm_user(sys.argv[2])
  elif sys.argv[1] == '-l':
    set_lang()
    list_users()
  else:
    helpexit()

def helpexit():
  print '\n',ident,'\n'
  print 'Usage: wb.py -s bboard doc    show document file structure'
  print '       wb.py -u user passwd   add user/password to local password file'
  print '       wb.py -r user          remove user from local password file'
  print '       wb.py -l               list password file content'
  sys.exit()

#############################################################################################
def wb_main():
  global cgimode,debug
  if os.path.basename(sys.argv[0]) == 'wt.py': debug=1

  if 'SERVER_SOFTWARE' in os.environ:
    cgimode=1        
    run_cgi()
  else:
    cgimode=0        
    run_standalone()

if __name__ == '__main__': wb_main()
