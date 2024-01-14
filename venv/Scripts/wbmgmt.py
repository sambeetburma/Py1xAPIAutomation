#!l:\py1xapiautomation\venv\scripts\python.exe

# wbmgmt.py  CGI based billboard management. Maintenance commands
#

import cgi
import sys,os
import fcntl
import re
import types
import string
import cPickle as pickle
import time,random

if not os.environ.has_key('REQUEST_URI'):
   print "\nThis program can only be run as CGI!!!\n"
   sys.exit()

if string.find(os.environ['REQUEST_URI'],'wbmgmt')>=0:
  import wb
  debug=wb.debug
else:
  import cgitb; cgitb.enable()        # enable debug HTML output
  debug=1
  import wt as wb

Document=wb.Document
Date=wb.Date
Attachment=wb.Attachment
                          # Get customization data from WB
root_dir = wb.root_dir
root_http = wb.root_http
do_log   = wb.do_log

LOCKFILE = 'wb.lock'
DELETED  = 'deleted' 
COMMASPACE = ', '

INFO = 0
ERROR  = 1

################################################################################
httpmatch=re.compile('http[s]?://[^`\'\"><)(\s]+',re.I)
def makelink(mtch):
  return '<a href="'+mtch.group(0)+'">'+mtch.group(0)+'</a>'

def urlcvt(text):
  t=httpmatch.sub(makelink, text)
  return t

################################################################################
def initfile(arc_dir):        # Read initialization file (wb.ini)
                              # merges definitions in wb.InitData and
                              # in vocabulary
  initname = os.path.join(arc_dir,'wb.ini')
  if not os.path.exists(initname): 
    p.log('warning. No init file: %s' % initname)
    return
    
  it={}
  try:
    p.log('reading initialization from: %s' % initname)
    execfile(initname,{},it)
  except:                    # no init file, use defaults
    page.error('error [%s] executing initialization file: %s'%(sys.exc_type,initname))
    wb.InitData['from_file']='' 
  else:
    wb.InitData.update(it)
    wb.set_lang(wb.InitData['language'])   # Redefine vocabulary (if needed)
    wb.InitData['from_file']=initname 
    if(debug): 
      wb.printinit(True,it)


############################################################################################
class Log:
  def __init__(self,rem_addr):
    self.rem_addr=rem_addr
    self.user=' ___ '
  def log(self,st):
    if logger: logger.info('%s@%s - %s' % (self.user,self.rem_addr,st))
    if debug: print '<br>PLOG - %s' % st
  def setu(self,user):
    self.user=user

############################################################################################
class Session:
  def __init__(self,bboard,ttl=wb.def_ttl):
    self.arc_dir=os.path.join(root_dir,bboard)
    self.ses_dir=os.path.join(root_dir,'_ses')
    self.bboard=bboard
    self.session_expir  = int(time.time()+ttl)
    self.suspended=0
    self.token=''
    self.userid=''

  def linkcvt(self):   # Converts links into HTML code
    self.doc.st_text=urlcvt(self.doc.st_text)

  def attach_file(self,orig_name,title,fobj):
    (rt,ext)=os.path.splitext(orig_name)
    if ext.lower() not in wb.accepted_types: 
      note=voc['ATCHILL'] + ': ' + orig_name
      p.log('illegal file type for attachment: %s'%orig_name)
      page.add_note(note,ERROR)
      note=voc['ALLWDATCH'], COMMASPACE.join(accepted_types)
      page.add_note(note,INFO)
      return 
    self.doc.max_id += 1
    atch_pref = 'ATC-'+self.doc.st_sid[4:]
    local_name= '%s-%3.3d%s' % (atch_pref,self.doc.max_id,ext.lower())
    atch_file= os.path.join(self.arc_dir,local_name)

    try:
      fout=open(atch_file,'w')
    except:
      note=voc['ATCHERR'] + ': ' + orig_name
      page.add_note(note,ERROR)
      p.log('error [%s] writing attachment file: %s (orig.name: %s)'%(sys.exc_type,atch_file,orig_name))
      return
      
    while 1:            # read in attachment file
      line = fobj.read(1024)
      if not line: break
      fout.write(line)
    fout.close()
    self.doc.attachments.append(wb.Attachment(title,orig_name,local_name,self.doc.max_id))
    note='%s %d: "%s" [%s]' % (wb.voc['ATCHMNT'],len(self.doc.attachments),title,orig_name)
    page.add_note(note,0)
    p.log('stored attachment %d: "%s" - orig. name:%s, local name:%s' % (len(self.doc.attachments),title,orig_name,atch_file))

  def rem_attach(self,at_id):
    at_id -= 1
    natc=len(self.doc.attachments)
    at = self.doc.attachments[at_id]
    atch_file= os.path.join(self.arc_dir,at.local_name)
    del self.doc.attachments[at_id]
    safeunlink(atch_file)
    return 


  def up_attach(self,att):
    idx=att-1

    if idx>0:
      save=self.doc.attachments[idx-1]
      self.doc.attachments[idx-1]=self.doc.attachments[idx]
      self.doc.attachments[idx]=save

  def dw_attach(self,att):
    natc=len(self.doc.attachments)
    idx=int(att)-1
    if idx<natc-1:
      save=self.doc.attachments[idx+1]
      self.doc.attachments[idx+1]=self.doc.attachments[idx]
      self.doc.attachments[idx]=save

  def docwrite(self):
    fname=os.path.join(self.arc_dir,self.doc.st_sid)
    try:
      fobj = open(fname, 'w')
      pickle.dump(self.doc,fobj,-1)
      fobj.close()
      p.log('document written to file: %s' % fname)
    except:
      p.log('error [%] writing file: %s'%(sys.exc_type,fname))
      page.add_note('['+sys.exc_type+'] %(WRERR)s '+fname,ERROR)

  def docload(self,docname):
    docfile=os.path.join(self.arc_dir,docname)
    try:
      self.doc=wb.docload(docfile)
    except:
      page.error('error [%s] reading file %s',(sys.exc_type,fname))
    else:
      self.new=False
      return True

  def newsession(self,userid,passwd,docname=None):
    self.token='S-%x'%int(time.time()*100)
    if not check_user(userid,passwd,wb.auth_mode):
      return False
    self.userid=userid
    if docname:
      if not self.docload(docname):
        return False
      else:
        p.log('created session. Token: %s - Document: %s'%(self.token,docname))
    else:
      self.doc=wb.Document()
      p.log('created session. Token: %s - Document: new'%self.token)
      self.new=True
    return True

  def save(self):
    fname=os.path.join(self.ses_dir,self.token)
    if not os.path.isdir(self.ses_dir):
       try:
          p.log('making working dir: %s' % self.ses_dir)
          os.makedirs(self.ses_dir)
       except:
          p.log('error [%s] making working dir: %s' % (sys.exc_type,self.ses_dir))
    try:
      fobj = open(fname, 'w')
      pickle.dump(self,fobj,-1)
      fobj.close()
      p.log('session saved to file: %s' % fname)
    except:
      p.log('error [%s] writing session file: %s'%(sys.exc_type,fname))
      page.add_note('Error [%s] %s : %s'%(sys.exc_type,wb.voc['WRERR'],fname),ERROR)

  def end(self):
    fname=os.path.join(self.ses_dir,self.token)
    p.log('end session: %s'%self.token)
    safeunlink(fname)
    
def opensession(token):
  fname=os.path.join(root_dir,'_ses',token)
  try:
    fd=open(fname)
    ret=pickle.load(fd)
    fd.close()
  except:
    ret=None
    p.log('error [%s] opening session: %s'%(sys.exc_type,fname))
  else:
    p.log('session %s reopened for user: %s'%(token,ret.userid))
    p.setu(ret.userid)
  return ret

def rem_all_atch(doc,arc_dir):
  cn=0
  for at in doc.attachments:
    atch_file= os.path.join(arc_dir,at.local_name)
    safeunlink(atch_file)
    del doc.attachments[cn]
    cn += 1
  return cn+1

def mov_all_atch(doc,arc_dir,rem_dir):
  cn=0
  for at in doc.attachments:
    atch_file= os.path.join(arc_dir,at.local_name)
    safemove(atch_file,rem_dir)
    del doc.attachments[cn]
    cn += 1
  return cn+1

#############################################################################################
def safemove(path,todir):       # moves files to given directory
  dir,fname=os.path.split(path)
  topath=os.path.join(todir,fname)
  try:
    os.rename(path,topath)
    p.log('file %s moved to: %s'%(path,topath))
  except:
    p.log('[%s] cannot move file %s to %s'%(sys.exc_type,path,topath))

#############################################################################################
def safeunlink(path):      # removes a file trapping errors in order to prevent program crash
  try:
    os.unlink(path)
    p.log('removed file: %s'%path)
  except:
    p.log('[%s] cannot remove file: %s'%(sys.exc_type,path))
    
#############################################################################################
def removeall(arc_dir,doc):        # removes a document and related attachments

  fname=os.path.join(arc_dir,doc.st_sid)
  if wb.InitData.get('delete_expired') and not debug:
    rem_all_atch(doc,arc_dir)
    safeunlink(fname)
  else:
    todir = os.path.join(arc_dir,DELETED)
    if not os.path.isdir(todir): 
      p.log('making directory for expired files: %s'%todir)
      os.mkdir(todir)
    mov_all_atch(doc,arc_dir,todir)
    safemove(fname,todir)

#############################################################################################
def text_item(name,size=0,value=''):
  text = '<input type=text name="%s"' % name
  if value: text += ' value="%s"' % value
  if size>0: text += ' size=%d' % size
  text += '>'
  return text

def file_item(name,size=0,value=''):
  text = '<input type=file name="%s"' % name
  if value: text += ' value="%s"' % value
  if size>0: text += ' size=%d' % size
  text += '>'
  return text

def textarea_item(name,rows=20, cols=80, value=''):
  text = '<textarea name="%s" rows=%d cols=%d>\n' % (name,rows,cols)
  if value: text += value
  text += '\n</textarea>'
  return text

def hidden_item(name,value):
  text='<input type=hidden name="%s" value="%s">'%(name,value)
  return text

#############################################################################################
#############################################################################################
class Page:
  def __init__(self):
    self.notes=[]
    self.out=''
    self.backlink=0

  def add(self,items):
    if type(items) == type(''):
      self.out += items + '\n'
    elif type(items) == type([]) or type(items) == type(()):
      self.out += '\n'.join(items)
    else:
      raise 'Type error',type(items)
    
  def add_note(self,msg,level=INFO):
    self.notes.append((level,msg))

  def back(self):
    self.backlink=1

  def end(self,back=0):
    if back: self.backlink=1
    if self.notes:
      print '<hr><b>%(NOTES)s:</b>' % wb.voc
      for xt in self.notes:
        if xt[0]: 
          print '<br><font color="red">',xt[1],'</font>'
        else:
          print '<br>',xt[1]
      print '<hr>'
    print self.out
    if self.backlink:
      act=accact
    else:
      act=''
    wb.footer(act)
    sys.exit()

  def error(self,msg):
    p.log(msg)
    print '<center><h2>',wb.voc['REPORT'],'</h2></center><hr>'
    print '<pre><b>%s</b></pre><hr>' % msg
    wb.environ()                # Printout environment
    wb.printinit(True)          # Printout Initialization file
    wb.show_input(action,form,args)
    wb.show_globals()
    sys.exit()
    

###############################################################################################
def doc_check(self):
  ret=1
                                        # Verify expiration
  if self.expir_required and not self.expir.defined():
    page.add_note(wb.voc['NOEXPIR'],ERROR)
    ret=0

                                        # Verify title
  self.st_title=self.st_title.strip()
  self.st_url=self.st_url.strip()

  if self.st_title == '':
    page.add_note(wb.voc['NOTITLE'],ERROR)
    ret=0
					# Verify body or singlew attachment
  self.st_text=self.st_text.strip()
  if self.st_style == 'TA':
    if not self.st_text:      # Document must have text body if style is TA
      page.add_note(wb.voc['NOBODY'],ERROR)
      ret=0

  if self.st_style == 'AO':   # Document must have one attachment, if style is AO
    if len(self.attachments) != 1:
      page.add_note(wb.voc['ATCHUNSP'],ERROR)
      ret=0

  if self.st_style == 'LO':   # Document must specify URL, if style is LO
    if not self.st_url:
      page.add_note(wb.voc['URLUNSP'],ERROR)
      ret=0
    
  return ret

#############################################################################
def my_str(k):
  if type(k) is str:
    return '"'+str(k)+'"'
  else:
    return str(k)

#############################################################################
# Functions to generate some forms
#############################################################################
def auth_head(bb='',root=0):          # returns authorization form header
  ret  = '<table border=1 cellpadding=5 width=100%><tr><td colspan=2 bgcolor="#ccffcc">\n'
  ret += '<form method="post" action="%s">\n' % action
  if bb:
    ret += hidden_item('st_bboard',bb)
  ret += hidden_item('st_checkauth','1')
  if root:
    ret += '&nbsp;&nbsp;<b>%(USERNAME)s: </b> <select name="st_userid">\n'%wb.voc
    for opt in wb.root_users:
      ret += '<option value="%s">%s</option>\n' %(opt,opt)
    ret += '</select>\n'
  else:
    ret += '&nbsp;&nbsp;<b>%(USERNAME)s: </b><input type=text name="st_userid">'%wb.voc
  ret += wb.NBSP10
  ret += '<b>%(PASSWD)s: </b><input type=password name="st_passwd"></td></tr>\n'%wb.voc
  return ret

######################################################################################
def auth_form0(bboard):             # Authorization form for new document definition
  ret = '<!-- Generated by: auth_form0() [wbmgmt]  -->\n'
  ret += wb.op_header ('%s: %s' % (wb.voc['NEWDOC1'],bboard))
  ret += auth_head(bboard)
  ret += hidden_item('do_newdoc','1')
  ret += '<tr><td>%(DOCSTYLE)s: '%wb.voc
  ret += '&nbsp;&nbsp;&nbsp;<input type=radio name="st_style" value="TA" checked>%(STY_TA)s\n'%wb.voc
  ret += '&nbsp;&nbsp;&nbsp;<input type=radio name="st_style" value="AO">%(STY_AO)s\n'%wb.voc
  ret += '&nbsp;&nbsp;&nbsp;<input type=radio name="st_style" value="LO">%(STY_LO)s\n'%wb.voc
  ret += '</td><td align=center> <input type=submit value="%(SUBMIT)s"></td></tr>\n'%wb.voc
  ret += '</form></table>\n'
  return ret

##########################################################################################
def auth_form1(bboard,root_dir):    # Authorization form for document editing or removing
                                     # It also shows a list of editable documents
  ret = '<!-- Generated by: auth_form1() [wbmgmt]  -->\n'
  ret += wb.op_header ('%s: %s' % (wb.voc['MODIFBB'],bboard))
  ret += auth_head(bboard) + '</table>\n'
  doc_dir=os.path.join(root_dir,bboard)
  docl=wb.document_list(doc_dir,wb.InitData['sort_order'])
  ret += '<blockquote>\n'
  for n in docl:
    ret += '<input type=radio name="st_sid" value="%s">' % n['st_sid']
    ret += '%s [%d] - <b>%s</b><br>\n' % (n['date'],n['st_sequence'],n['st_title'])
  ret += '</blockquote><center>\n'
  ret += '<input type=submit name="do_edit" value="%(MODDOC1)s" '%wb.voc
  ret += 'style="background:#66cc66">' + wb.NBSP10 + '<input type=submit name="do_remove" value="%(RMDOC)s" '%wb.voc
  ret += 'style="background:red"> </center></form>\n'
  return ret

######################################################################################
def auth_form2(bboard):             # Authorization form for maintenance operations
  ret = '<!-- Generated by: auth_form2() [wbmgmt]  -->\n'
  ret += wb.op_header ('%s: %s' % (wb.voc['MAINTN1'],bboard)) + auth_head(bboard)
  ret += hidden_item('do_manut','1')
  ret += '<tr><td width=90%%>&nbsp;</td><td align=center><input type=submit value="%(SUBMIT)s"></td></tr>'%wb.voc
  ret += '</form></table>'
  return ret

######################################################################################
def auth_form3():                    # Authorization form for new billboard creation
  ret = '<!-- Generated by: auth_form3() [wbmgmt]  -->\n'
  ret += wb.op_header (wb.voc['BBCREA']) + auth_head(root=1)
  ret += '<tr><td> %s: ' %wb.voc['NEWBBNAME']
  ret += hidden_item('do_newbb','1')
  ret += text_item('st_bboard',30)
  ret += wb.NBSP5+'<input type=submit value="%(SUBMIT)s"></td></tr>\n'%wb.voc
  ret += '</form></table>\n'
  return ret

def auth_form4(bboard):     # Form to allow editing of billboard initialization file
  inifile = os.path.join(root_dir,bboard,'wb.ini')
  try:
    fd=open(inifile)
  except:
    text=''
    page.add_note(wb.voc['NOINIT'])
    p.log('new config file %s'%inifile)
    text = '# Default configuration\n\n'
    ks=wb.InitData.keys()
    ks.sort()
    for k in ks:
      text += cgi.escape('%s = %s\n' % (k,my_str(wb.InitData[k])))
  else:
    p.log('editing file %s'%inifile)
    text=cgi.escape(''.join(fd.readlines()))
    fd.close()

  ret = '<!-- Generated by: auth_form4() [wbmgmt]  -->\n'
  ret += wb.op_header ('%s: <i>%s</i>'%(wb.voc['EDITINI'],bboard)) + auth_head(bboard,root=1)
  ret += '<table border=2 cellpadding=5>\n'
  ret += '<tr><td>\n'
  ret += textarea_item('st_wbini',cols=120,rows=50,value=text)+'</td></tr>\n'
  ret += '<tr><td align="center">\n'
  ret += '<input type=submit name="do_editini" value="'+wb.voc['SUBMIT']+'" style="background:#aaaaff">'
  ret += '</td></tr></table></form>\n'
  return ret

def auth_form5(bboard):     # Form to allow billboard removal
  p.log('removing billboard %s'%bboard)
  ret = '<!-- Generated by: auth_form5() [wbmgmt]  -->\n'
  ret += wb.op_header ('%s %s'%(wb.voc['REMBBL'],bboard))+ auth_head(bboard,root=1)
  ret += '<table border=2 cellpadding=5 width=100%>'
  ret += '<tr><td align="center">'
  ret += '<input type=submit name="do_rembb" value="'+wb.voc['CONFREM']+'" style="background:red">'
  ret += '</td></tr></table></form>\n'
  return ret

    
###############################################################################################
#  Form making methods. 
###############################################################################################
def form_head(s):                                   # common header for many forms
  ret = '<form method="post" enctype="multipart/form-data" action="%s">' % action
  ret += hidden_item('st_bboard',s.bboard) + '\n'
  ret += hidden_item('st_sid',s.doc.st_sid) + '\n'
  ret += hidden_item('st_token',s.token) + '\n'
  return ret


###############################################################################################
def preview_form(s):
  ok=doc_check(s.doc)
  ret = '<!-- Generated by: preview_form() [wbmgmt]  -->\n'
  ret += '<hr>\n'
  ret += s.doc.repr(s.bboard,http_path)
  ret += '<hr>\n'
  if s.new:
    chkd='checked'
  else:
    chkd=''
  ret += form_head(s)
  for at in s.doc.attachments:
    ret += hidden_item('st_att_%3.3d'%at.id,'1') + '\n'
  ret += '<table cellpadding=10 border=1>'
  ret += '<tr><td><input type=submit name="do_resume" value="%s" style="background:#66cc66"></td>\n' % wb.voc['MODIFU'] 
  if ok:
    disable=''
  else:
    disable='DISABLED'
  ret += '<td><input type=submit name="do_publish" value="%s" style="background:#aaaaff" %s>\n' % (wb.voc['PUBLISH'],disable)
  if wb.InitData['mail_to']:
     ret += '&nbsp;&nbsp; <input type=checkbox name=st_notify %s>%s</td>\n' % (chkd,wb.voc['DONOTIFY'])
  ret += '<td><input type=submit name="do_canc_edit" value="%s" style="background:red"></td>\n' % wb.voc['CANCEL']
  ret += '</tr></table></form>\n'
  return ret
  

#############################################################################################
def del_confirm_form(s):   # Form to ask confirmation after delete request
  ret = '<!-- Generated by: del_confirm_form() [wbmgmt]  -->\n'
  ret += wb.op_header('%s  <i>%s:%s</i>'%(wb.voc['RMREQST'],s.bboard,s.doc.st_sid)) 
  ret += '<hr>\n'
  ret += s.doc.repr(s.bboard,http_path)
  ret +=  '<hr>\n'
  ret += form_head(s)
  ret +=  '<center>'
  ret +=  '<input type=submit name="do_conf_remove" value="%s" style="background:red">' % wb.voc['CONFREM']
  ret +=  wb.NBSP10
  ret +=  '<input type=submit name="do_canc_rem" value="%s" style="background:#66cc66">\n' % wb.voc['CANCEL']
  ret +=  '</center></form>\n'
  return ret

###############################################################################################
def edit_form(s,max_sequence=(-1)):     # Form to allow editing of a document
  ret = '<!-- Generated by: edit_form() [wbmgmt]  -->\n'
  ret += form_head(s)
  html_checked = ''
  if s.doc.st_html: html_checkd = 'checked'
  expir=''
  if s.doc.expir.defined(): expir=s.doc.expir.__str__()
  ret += '<table border=2 cellpadding=5>\n'
  if s.new:
    ret += '<tr><th bgcolor="#aaaaff">%s: <i>%s</i></th></tr>\n'%(wb.voc['ADDDOC'],s.bboard)
  else:
    ret += '<tr><th bgcolor="#aaaaff">%s <i>%s:%s</i></th></tr>\n'% (wb.voc['MODDOC'],s.bboard,s.doc.st_sid)
  ret += '<tr><td><table>\n'
  ret += '        <tr><td><b>%s: </b></td><td> %s </td></tr>\n' % (wb.voc['TITLE'], text_item('st_title',size=70,value=s.doc.st_title))
  ret += '        <tr><td><b>%s: </b></td><td> %s </td></tr>\n' % (wb.voc['AUTHOR'],text_item('st_author',size=70,value=s.doc.st_author))
  ret += '        <tr><td><b>%s: </b></td><td> %s </td></tr>\n' % (wb.voc['DATE'], text_item('st_date',size=10,value=s.doc.date))
  ret += '        <tr><td><b>%s: </b></td><td> %s </td></tr>\n' % (wb.voc['EXPIRTN'], text_item('st_expir',size=10,value=expir))
  vv='%d'%s.doc.st_sequence
  ret += '        <tr><td><b>%s: </b></td><td> %s </td></tr>\n' % (wb.voc['SEQUENCE'], text_item('st_sequence',size=10,value=vv))
  ret += '        </table></td></tr>\n'

  manyatchs=0
  if s.doc.st_style == 'TA':
    manyatchs=1
    ret += '<tr><td><table><tr><td><b>%(TEXT)s:</b></td>'%wb.voc
    ret += '<td><font size=-1>%s</font><input type=checkbox name="st_html" %s></td>'%(wb.voc['HTMLFMT'],html_checked)
    ret += '<td align=right width=50%%><input type=submit name="do_convert" value="%s"></td></tr>\n' % wb.voc['MAKELINKS']
    ret += '<tr><td colspan=3>'
    ret +=  textarea_item('st_text',value=s.doc.st_text)+'</td></tr></table></td></tr>\n'

  if s.doc.st_style == 'LO':
    ret +=  '<tr><td><b>%(LINK)s:</b> '%wb.voc
    ret +=  text_item('st_url', size=50, value=s.doc.st_url)
    ret +=  '</td></tr>\n'

  if s.doc.st_style != 'LO':
    if s.doc.attachments:
      ret +=  '<tr><td bgcolor="#aaaaaa">%(ATCHMNTS)s:<br>'%wb.voc
      nal=len(s.doc.attachments)
      if nal>0: ret += '<table>\n'
      for al in range(nal):
        at=s.doc.attachments[al]
        ret +=  '<tr><td>%2d.</td><td><a href="%s?cmd=del_att&att=%3.3d&bb=%s&token=%s"><img src=%s/_img/del.gif></a>' % (al+1,action,at.id,s.bboard,s.token,root_http)
        if al>0:
          ret +=  '<a href="%s?cmd=up_att&att=%3.3d&bb=%s&token=%s"><img src=%s/_img/up.gif></a>' % (action,at.id,s.bboard,s.token,root_http)
        if al<nal-1:
          ret +=  '<a href="%s?cmd=dw_att&att=%3.3d&bb=%s&token=%s"><img src=%s/_img/do.gif></a>' % (action,at.id,s.bboard,s.token,root_http)
        ret +=  '<td><td> %s [<i>%s</i>]</td></tr>\n' % (at.title,at.orig_name)
      if nal>0: ret += '</table>\n'
      ret +=  '</td></tr>\n'
    ret +=  '<tr><td bgcolor="#dddddd">'

    if manyatchs:      # style allows more than one attachment
      ret +=  '     <table cellpadding=5><tr><td align=center>%s</td>\n'%wb.voc['ATCHTIT']
      ret +=  '<td align=center>%(SPECATCH)s</td><td></td></tr>\n'%wb.voc
      next_atch=len(s.doc.attachments)+1
      ret +=  '    <tr><td>%s</td>'%text_item('st_attachtitle',size=20,value=wb.voc['ATCHMNT']+' %d'%next_atch)
      ret +=  '    <td>%s</td>'%file_item('st_filetoattach', size=40)
      ret +=  '    <td><input type=submit name="do_attach" value="%s" style="background:#6666cc"></td></tr></table>\n' % wb.voc['ATTACH']
    else:          # style requires only one attachment
      if len(s.doc.attachments) == 0:
        ret +=  '     <table cellpadding=5><tr><td align=center>%s</td>\n'%wb.voc['SPECATCH']
        ret +=  '    <td>%s</td></tr></table>\n'%file_item('st_filetoattach', size=40)

    ret +=  '</td></tr>\n'

  ret +=  '<tr><td align="center">'
  if s.doc.st_style=='TA':
    ret +=  '<input type=submit name="do_preview" value="%s" style="background:#66cc66">'% wb.voc['PREVIEW']
  else:
    ret +=  '<input type=submit name="do_publish" value="%s" style="background:#aaaaff">' % wb.voc['PUBLISH']
  ret +=  wb.NBSP10
  ret +=  '<input type=submit name="do_canc_edit" value="%s" style="background:red">' % wb.voc['CANCEL']
  ret +=  '</td></tr></table></form>\n'
  return ret

#############################################################################################
def update_document(s,form,convert=0):   # Updates document field from form input
  p.setu(s.userid)
  p.log('updating document %s'%s.doc.st_sid)
  if 'st_text' in form:
    s.doc.st_text = form.getvalue('st_text').rstrip()
    if convert: s.linkcvt()
  if 'st_title' in form:
    s.doc.st_title = form.getvalue('st_title').strip()
  if 'st_author' in form:
    s.doc.st_author = form.getvalue('st_author').strip()
  if 'st_sequence' in form:
    s.doc.st_sequence = int(form.getvalue('st_sequence'))
  sdate=form.getvalue('st_date')
  s.doc.date=wb.Date(sdate)
  sdate=form.getvalue('st_expir')
  if sdate: s.doc.expir=wb.Date(sdate)
  s.doc.st_html=form.getvalue('st_html')
  if 'st_url' in form:
    s.doc.st_url=form.getvalue('st_url')
                                            # Manage attach request
  if 'st_filetoattach' in form:
    atch= form['st_filetoattach']
    atch_title=form.getfirst('st_attachtitle')
    atch_name=atch.filename
    if atch_name:
      atch_read=atch.file
      s.attach_file(atch_name,atch_title,atch_read)
    else:
      if 'do_attach' in form:
        page.add_note(wb.voc['ATCHUNSP'],ERROR)

#############################################################################################
def make_document(data):               # Create basic document from generic input data
  doc=Document()
  if data.has_key('st_text'):
    doc.st_text = form.getvalue('st_text').rstrip()
#    if convert: s.linkcvt()
  else:
    err_exit('!!!')

  if data.has_key('st_title'):
    doc.st_title = form.getvalue('st_title').strip()
  else:
    err_exit('!!!')

  if data.has_key('st_author'):
    s.doc.st_author = form.getvalue('st_author').strip()

  if data.has_key('st_sequence'):
    s.doc.st_sequence = int(form.getvalue('st_sequence'))
  else:
    s.doc.st_sequence = 0

  if data.has_key('st_date'):
    sdate=form.getvalue('st_date')
    doc.date=wb.Date(sdate)

  sdate=form.getvalue('st_expir')
  if sdate: doc.expir=wb.Date(sdate)
  doc.st_html=form.getvalue('st_html')
   

#############################################################################################
def check_passwd_local(userid,passwd): # Check userid authorizations in local password file
  import sha

  ok=0
  pwfile =  os.path.join(root_dir,wb.pwname)
  p.log('reading password file: "%s"'% pwfile)
  users={}
  try:
    execfile(pwfile,{},users)
  except:                    # No password file: 
    p.log('error [%s] reading password file: "%s"'% (sys.exc_type,pwfile))
  else:
    a=sha.new(userid)
    a.update(passwd)
    ok = (users.get(userid) == a.hexdigest())

  return ok


#############################################################################################
def check_passwd_unix(userid,password):  # Check userid authorizations in system password file
  import crypt
  import pwd as pw
                                         # first authenticate user
  p.log('checking user against /etc/passwd')
  try:
    cryptedpw = pw.getpwnam(userid)[1]
  except:
    p.log('error [%s] in pwd.getpwnam("%s")'% (sys.exc_type,userid))
    ok=0
  else:
    ok = (crypt.crypt(password, cryptedpw) == cryptedpw)

  return ok


#############################################################################################
def check_passwd_shadow(userid,password):  # Check userid authorizations in system shadow file
  import crypt
  try:
     import spwd 
  except:
     p.log('error: cannot import spwd. Shadow passwords not supported')
     return False
                                         # first authenticate user
  p.log('checking user against /etc/shadow')
  try:
    cryptedpw = spwd.getspnam(userid)[1]
  except:
    p.log('error [%s] in spwd.getspnam("%s")'% (sys.exc_type,userid))
    ok=0
  else:
    usrpw = crypt.crypt(password, cryptedpw)
    p.log('user spec:%s  -  from shadow:%s'%(usrpw,cryptedpw))
    ok = (usrpw == cryptedpw)

  return ok

#############################################################################################
def check_passwd_nis(userid,password):  # Check userid authorizations agains NIS passwd
  import crypt
  try:
     import nis 
  except:
     p.log('error: cannot import nis. NIS passwords not supported')
     return False
                                         # first authenticate user
  p.log('checking user against NIS passwd')
  try:
    cryptedpw=nis.match(userid,'passwd.byname').split(':')[1]
  except:
    p.log('error [%s] in pwd.getpwnam(%s)'% (sys.exc_type,userid))
    ok=False
  else:
    usrpw = crypt.crypt(password, cryptedpw)
    ok = (usrpw == cryptedpw)

  return ok


#############################################################################################
def auth_user(userid,passwd,mode):    # Authenticate user/passwd
  if passwd is None: passwd=''

  if not userid:
    p.log('no user ID specified')
    page.add_note(wb.voc['NOUSER'],ERROR)
    return False

  ok=False

  lmode = mode
  if mode=='unix':
    ok=check_passwd_unix(userid,passwd)
  elif mode=='shadow':
    ok=check_passwd_shadow(userid,passwd)
  elif mode=='nis':
    ok=check_passwd_nis(userid,passwd)

  if not ok:
    ok=check_passwd_local(userid,passwd)
    lmode='local'

  if ok:
    p.log('user %s authenticated (from: %s)'% (userid,lmode))
  else:
    p.log('invalid userid/password. user: %s (mode:%s)'% (userid,mode))
  return ok
    

#############################################################################################
def check_user(userid,password,mode,root=0):  # Check userid authorizations with specified mode
                                              # first authenticate user
  ok=auth_user(userid,password,mode)
    
  if ok:                                 # check if user is in user list
    users=list(wb.root_users)
    if not root: users.extend(wb.InitData['allowed_users'])
    ok = userid in users
    if not root and wb.InitData['allowed_users'][0].lower() == 'everybody':
      ok=True

  if ok:
    p.log('granted access to user %s'% userid)
  else:
    p.log('denied access to user %s'% userid)
    print '<h2>%s: <i> %s </i></h2>' % (wb.voc['DENIED'], userid)

  return ok


#############################################################################################
def clean_bboard(arc_dir,userid,passwd):     # Clean given bboard: 
                                             #   - removes expired documents,
                                             #   - removes temporary files
                                             #   - removes dangling attachments
                                             #   - removes suspended sessions
  if cgimode:
    print '&nbsp;&nbsp;&nbsp;&nbsp;%s: %s<br>' % (wb.voc['CLEANG'],arc_dir)
  else:
    print '   %s: %s' % (wb.voc['CLEANG'],arc_dir)

  bboard=os.path.split(arc_dir)[-1]
  page.add_note(wb.voc['MAINTN2'],0)
  p.log('removing expired documents from bboard: %s'%arc_dir)
  count=0
  files=filter(lambda x: x[0:4]=='DOC-', os.listdir(arc_dir))
  for f in files:
    fn=os.path.join(arc_dir,f)
    doc=wb.docload(fn)
    if doc.expir.expired():
      count += 1
      removeall(arc_dir,doc)
  page.add_note('&nbsp;&nbsp;&nbsp;&nbsp;  %s: %d' % (wb.voc['EXPDDOC'],count),0)

  p.log('removing dangling attachments in dir: %s'%arc_dir)
  count=0
  for f in files:
    if f[0:4] == 'ATC-':
      docn=os.path.splitext('DOC-'+ f[4:])[0][0:-4]  # docn is the file name of document 
                                                   # containing the attachemnt,
                                                   #  eg: DOC-29D581BBEL
      if docn not in files: 
        count +=1
        safeunlink(os.path.join(arc_dir,f))

  page.add_note('&nbsp;&nbsp;&nbsp;&nbsp; %s: %d' % (wb.voc['DANGLATCH'],count),0)

  ses_dir=os.path.join(root_dir,'_ses')
  files=os.listdir(ses_dir)
  p.log('removing expired sessions')
  count=0
  for f in files:
    if f[0:2] == 'S-':
      fname = os.path.join(ses_dir,f)
      try:
        fd=open(fname)
        s=pickle.load(fd)
        fd.close()
      except:
        pass
      else: 
        if s.session_expir  < int(time.time()):
          p.log('removing expired session: %s' % f)
          safeunlink(fname)
          count += 1
        else:
          p.log('session: %s still valid. Not removed' % f)

  page.add_note('&nbsp;&nbsp;&nbsp;&nbsp; %s: %d' % (wb.voc['EXPDSES'],count),0)
  page.back()
  return 1

#############################################################################################
def crea_bboard(bboard,userid,passwd):     # Create a new billboard
  import shutil
  if not bboard: bboard=''
  p.log('creating new billboard: %s'%bboard)

  if not check_user(userid,passwd,wb.auth_mode,root=True):
    return False

  if not bboard or bboard[0]=='_' or bboard[0]=='.':
    p.log('illegal billboard name: %s' % bboard)
    page.add_note('%s: %s'%(bboard,wb.voc['BBILLNAME']),1)
    return False

  dirpath = os.path.join(root_dir,bboard)
  try:
    os.mkdir(dirpath)
    p.log('created directory: %s'%dirpath)
  except:
    p.log('error creating directory: %s'%dirpath)
    page.add_note('%s: %s' % (wb.voc['BBCREAERR'],dirpath))
    return False
  frompath = os.path.join(root_dir,'wb.ini')
  p.log('copying file %s to: %s' % (frompath,dirpath))
  try:
    shutil.copy(frompath,dirpath)
  except:
    p.log('error [%s] copying file wb.ini to: %s'%(sys.exc_type,dirpath))
    page.add_note('%s: %s' % (wb.voc['BBINITERR'],dirpath),0)
    return False

  return True

#############################################################################################
def rem_bboard(bboard,userid,passwd):
    p.log("Removing billboard %s (Not yet implemented)" %bboard)
    page.add_note(wb.voc['TBI'],ERROR)

#############################################################################################
def write_init(arc_dir,text):     # Write new config file
  import shutil
  bckfile=os.path.join(arc_dir,'wb.bck')
  inifile=os.path.join(arc_dir,'wb.ini')
  tmpfile=os.path.join(arc_dir,'wb.tmp')
  p.log('saving old init file into: %s' % bckfile)
  try:
    shutil.copy(inifile,bckfile)
  except:
    p.log('old init file not saved')
  p.log('writing new init file: %s' % inifile)
  of=open(tmpfile,'w')
  of.write(text)
  of.close()
  os.rename(tmpfile,inifile)
  

#############################################################################################
fmt0 = '<h3> %s: %s (%s: %s)</h3>\n'
fmt1 = '<ul>\n'
fmt2 = '<li> %s: <b>%s</b>\n'
fmt3 = '<li> %s (%s: %s) - %s\n'
fmt4 = '</ul>\n'
fmt5 = '</ul><hr>%s:<br><table border=1 cellpadding=5>%s</table>\n'

def show_info(arc_dir,bb):     # Shows some information related to given bboard

  ret='<!-- Generated by show_info() [wbmgmt]  -->\n'
  ret += wb.op_header('%s: <i>%s</i>' % (wb.voc['BBINFO'],bb))

  dl=wb.document_list(arc_dir)
  
  ret += fmt1 
  ret += fmt2 % (wb.voc['LANGF'], wb.voc['LANGUAGE'])
  ret += fmt2 % (wb.voc['NDOCS'], len(dl))
  ret += fmt2 % (wb.voc['ALLWDUSR'], COMMASPACE.join(wb.InitData['allowed_users']))
  ret += fmt2 % (wb.voc['NOTIFTO'], COMMASPACE.join(wb.InitData['mail_to']))
  ret += fmt2 % (wb.voc['ALLWDATCH'], ' '.join(wb.accepted_types))
  
  exp=filter(lambda x: x['expir'].expired(),dl)
  ret += fmt2 % (wb.voc['EXPDDOC'],'')
  if exp:
    ret += fmt1
    for d in exp:
      ret += fmt3 % (d['date'],wb.voc['EXPIRD'],d['expir'],d['st_title'])
    ret += fmt4
  else:
    ret += '0'
  ret += fmt5 % (wb.voc['OPERS'],wb.op_list(bb,accact,action))
  return ret

#############################################################################################
def set_log(log_dir):       # Set up logging support 
                            # The p.log routine is used to write log records
  import logging
  import logging.handlers
  global logger

  logger = logging.getLogger('wb')
  logfile=os.path.join(log_dir,'wb.log')
  hdlr = logging.handlers.RotatingFileHandler(logfile,'a',wb.log_size,wb.log_number)
  formatter = logging.Formatter('%(asctime)s %(message)s')
  hdlr.setFormatter(formatter)
  logger.addHandler(hdlr) 
  logger.setLevel(logging.INFO)

#############################################################################################
def notify(bboard,doc,new):      # Send mail to the list of addresses to be notified
  import smtplib
  from email.MIMEText import MIMEText

  items = {'TITLE'    : doc.st_title,
           'AUTHOR'   : doc.st_author,
           'SEQNUM'   : doc.st_sequence,
           'BBOARD'   : bboard,
           'DATE'     : doc.date,
           'HREF'     : '%s?cmd=show&bb=%s&doc=%s'%(full_accact,bboard,doc.st_sid) }
  items['EXPIR']=wb.expir_str(doc.expir)
  sender= wb.InitData['mail_from']
  toaddrs=wb.InitData['mail_to']

  if new:
    msg=MIMEText('\n'.join(wb.InitData['mail_new']) % items)
    msg['Subject']='%(SADDED)s: ' % wb.voc + bboard
  else:
    msg=MIMEText('\n'.join(wb.InitData['mail_update']) % items)
    msg['Subject']='%(SMODIF)s: ' %wb.voc + bboard

  msg['From']=sender
  msg['To']=COMMASPACE.join(toaddrs)
  msg.epilogue=''
  try:
    s=smtplib.SMTP(wb.smtphost)
    s.sendmail(sender, toaddrs, msg.as_string())
    s.quit()
  except:
    exc_type=str(sys.exc_type)
    errst = 'email notification error: [%s]\n'%sys.exc_type + \
            '     sender: %s\n' % sender + \
            '         to: %s\n' % toaddrs + \
            '   smtphost: %s\n' % wb.smtphost
    page.error(errst)

  p.log('sent notification to %s'% msg['To'])

#############################################################################################
def view_logfile(log_dir):                    # Show log file content
  log_match=re.compile('wb.log')
  files=filter(log_match.match,os.listdir(log_dir))
  files.sort()
  if files:
    ret = '<h3>'+ wb.voc['SELLOG']+ '</h3><ul>\n'
    for k in files:
      ret += '<li><a href=%s/_var/%s>%s</a>\n' %(root_http,k,k)
    ret += '</ul>\n'
  else:
    ret += '<h3>' + wb.voc['NOLOG']+'</h3>\n'
  return ret


#############################################################################################
def show_lang(rdir):
  import copy

  ret = '<h3>%s: <i>%s</i></h3>' % (wb.voc.get('DEFLANG'),wb.voc.get('LANGUAGE'))
  saveverb=wb.voc.get('AVLANGS')

  files=os.listdir(rdir)
  files=filter(lambda x: x[0:6]=='_lang_',files)
  allvoc={}
  vocnames=[]
  for f in files:
    wb.set_lang(f[-2:])
    allvoc[f]=copy.copy(wb.voc)
    vocnames.append('%s:<i>%s</i>' %(f,wb.voc['LANGUAGE']))

  vocs=allvoc.keys()

  ret += '<h3>%s: %s</h3>\n'%(saveverb, COMMASPACE.join(vocnames))
  ret += '<table border=1>\n'

  allkeys = {}
  for k in vocs: 
    allkeys.update({}.fromkeys(allvoc[k].keys(),1))
  allkeys = allkeys.keys()
  allkeys.sort()
  for j in allkeys:
    ret += '<tr><td><b>%s:</b></td><td>' % j
    for k in vocs:
      try:
        term=allvoc[k][j]
      except:
        term='<font color="red">????</font>'
      ret += '    %s: <i>%s</i><br>' % (k,term)
    ret += '</td></tr>\n'
  ret += '</table>\n'

  return ret



#############################################################################################
def clean_all(root_dir):                   # Clean all billboards
  list=dirlist(root_dir)
  for l in list:
    arc_dir=os.path.join(root_dir,l)
    clean_bboard(arc_dir)

#############################################################################################
def mgmt_main():
  global cgimode,debug,language_file,logger,page,p,form,args
  global action,accact,full_accact,do_log,user,http_path,help_path

  if os.path.basename(sys.argv[0]) == 'wtmgmt.py': debug=1
  if debug: 
    import cgitb; cgitb.enable()        # enable debug HTML output

  rem_addr=os.environ['REMOTE_ADDR']    # Extract "action" from input data

  logger=None
  page = Page()
  cgimode=1        

  log_dir=os.path.join(root_dir,'_var')
  p=Log(rem_addr)

  wb.header()
    
  form=cgi.FieldStorage()
  req_uri = os.environ['REQUEST_URI']
  request = req_uri.split('?')
  action = request[0]
  accact=action[:-7]+'.py'
  if len(request)>1:
    args=request[1].split('&')
  else:
    args=[]

  wb.set_lang()    # set default vocabulary

  if debug: 
    wb.debug=True
    wb.environ()                        # Printout environment
    wb.printinit(True)                  # Printout Initialization data
    wb.show_input(action,form,args)
    wb.show_globals()

  full_accact = 'http://'+os.environ['SERVER_NAME']+accact

  if do_log: set_log(log_dir)       # start logging

  if os.environ['REQUEST_METHOD'] == 'GET':
                                             # Request method is GET: session begins here
    p.log('##### wb version %s -  begin CGI [GET]' % wb.Version)
                                    # Extract input arguments
    if len(request) == 1:   # when called without input arguments, return to BB list
      p.log("no input argument: wrong access")
      page.add_note('<b>%s</b>' %wb.voc['WRONGACC'])
      page.end(1)

    indata={}
    for a in args:
      k,v = a.split('=')
      indata[k]=v

    cmd=indata['cmd']
    p.log('input command: %s' % cmd)

    if cmd == 'log':      # view log files
      page.add(view_logfile(log_dir))
      page.end(1)

    if cmd == 'voc':      # view vocabularies
      page.add(show_lang(root_dir))
      page.end(1)

    if cmd == 'newbb':      # create a new billboard
      page.add(auth_form3())
      page.end(1)

    bboard=indata['bb']

    arc_dir=os.path.join(root_dir,bboard)   # get bboard directory path

    if debug: p.log('arc_dir: %s'%arc_dir)

    if not os.path.exists(arc_dir): 
      page.error('no billboard directory: %s'% arc_dir)

    initfile(arc_dir)

    http_path=root_http + '/' + bboard

                                  # Execute input commands
    if cmd == 'new':              # New document request
      page.add(auth_form0(bboard))
      page.end(1)

    if cmd =='edit' :           # Modify document request
      page.add(auth_form1(bboard,root_dir))
      page.end(1)

    if cmd == 'info':           # Show bboard info
      page.add(show_info(arc_dir,bboard))
      page.end(1)

    if cmd == 'clean':          # Perform bboard maintenance
      page.add(auth_form2(bboard))
      page.end(1)

    if cmd == 'editini':        # Edit billboard initialization file
      frm=auth_form4(bboard)
      if frm:
        page.add(frm)
      else:
        page.add_note('%s: <i>%s</i>' % (wb.voc['NOINIT'],bboard))
      page.end(1)

    if cmd == 'rembb':        # remove a billboard
      page.add(auth_form5(bboard))
      page.end(1)

#   Attachment operations

    att=int(indata['att'])
    token=indata['token']
    
    s=opensession(token)
    if s:
      if cmd == 'del_att':
        s.rem_attach(att)
      elif cmd == 'up_att':
        s.up_attach(att)
        p.log('attachment %d moved up'%att)
      elif cmd == 'dw_att':
        dw_attach(att)
        p.log('attachment %s moved down'%att)
      else:
        p.log('received wrong command: %s'%cmd)
        page.error('Illegal command')

      page.add(edit_form(s))
      s.save() 
    page.end()                    # terminate session

  ########################################################################################
                                  # We get here only for request method == POST 
  p.log('##### wb version %s -  begin CGI [POST] step' % wb.Version)
  
  bboard=form.getfirst('st_bboard')
  arc_dir=os.path.join(root_dir,bboard)   # get bboard directory path
  if debug: p.log('arc_dir: %s'%arc_dir)
  if bboard:
    http_path=root_http + '/' + bboard
    initfile(arc_dir) 

  userid=form.getfirst('st_userid')
  if userid: p.setu(userid)

#---------------------------------------
  if 'do_newbb' in form:                  # Create new billboard
    passwd=form.getfirst('st_passwd')     # get password
    if crea_bboard(bboard,userid,passwd):
      page.add_note('%s: <i>%s</i>' %(wb.voc['BBCREATED'],bboard),0)
    page.back()
    page.end()

  st_sid=form.getvalue('st_sid')

#---------------------------------------
  if 'do_newdoc' in form:                            # New document request
    p.log('new document request for bb:%s'%bboard)
    s=Session(bboard)
    passwd=form.getfirst('st_passwd')     # get password
    if s.newsession(userid,passwd):
      s.doc.st_style=form.getvalue('st_style')
      s.doc.st_sequence=maxsequence(arc_dir)+1
      page.add(edit_form(s))
      s.save()                          # Store new (empty) document
    else:
      page.back()
    page.end()

  token=form.getvalue('st_token')
#---------------------------------------
  if 'do_edit' in form:                 # edit request
    p.log('edit request for document: %s'%st_sid)
    s=Session(bboard)
    passwd=form.getfirst('st_passwd')     # get password
    if st_sid:
      if s.newsession(userid,passwd,st_sid):
        page.add(edit_form(s))           # show the edit form
        s.save()                         # store modified document (temporary)
      else:
        page.back()
    else:
      page.back()
      p.log('no document selected')
      page.add_note(wb.voc['NOSEL'],0)
    page.end()

#---------------------------------------
  if 'do_canc_edit' in form:                # Edit operation cancelled
    p.log("document update cancel request")
    s=opensession(token)
    if s:
      page.add_note(wb.voc['OPCANC'])
      rem_all_atch(s.doc,arc_dir)   # Remove all attachments
      s.end()
    page.end(1)

#---------------------------------------
  if 'do_resume' in form:                   # Resume edit request
    p.log('resume edit request for document: %s:%s'%(arc_dir,st_sid))
    s=opensession(token)
    if s:
      page.add(edit_form(s)) # show the edit form
      s.save()                      # store modified document (temporary)
    else:
      page.back()
    page.end()
#---------------------------------------

  if 'do_preview' in form:                    # preview request
    p.log('preview request for document: %s'%st_sid)
    s=opensession(token)
    if s:
      update_document(s,form)      # Merge form data into document
      page.add(preview_form(s))
      s.save()                     # store modified document (temporary)
    else:
      page.back()

    page.end()

#---------------------------------------
  if 'do_publish' in form:       # publish request
    p.log('publish request for document: %s'%st_sid)
    if form.has_key('st_notify'): 
      p.log('notification requested. Notification list: %s' % ','.join(wb.InitData['mail_to']))
    else:
      p.log('notification disabled')
    s=opensession(token)
    if s:
      update_document(s,form)      # Merge form data into document
      if doc_check(s.doc):
        p.log('document check OK')
        new=s.new
        s.docwrite()                  # store modified document (final)
        page.add_note('%s: "%s" &nbsp; <font size=-1>(ID: <i>%s</i>)</font></h3>' % \
                     (wb.voc['DOCPUBL'],s.doc.st_title, s.doc.st_sid))
        if wb.InitData['mail_to'] and form.has_key('st_notify'): 
          notify(bboard,s.doc,new)
        s.end()
        page.back()
      else:
        p.log('document check not OK. Publication delayed')
        page.add(edit_form(s))   # show the edit form
        s.save()                 # store modified document (temporary)
    else:
      page.back()
    page.end()

#---------------------------------------
  if 'do_convert' in form:               # Link convert request
    p.log('link convert request (doc: %s)'%st_sid)
    s=opensession(token)
    if s:
      update_document(s,form,convert=1) # merge form data into document
      page.add(edit_form(s))
      s.save()                          # store modified document (temporary)
    else:
      page.back()
    page.end()
#---------------------------------------
  if 'do_attach' in form:               # Attach request (handled by update_document)
    p.log('attach request (doc: %s)'%st_sid)
    s=opensession(token)
    if s:
      update_document(s,form)      
      page.add(edit_form(s))     # merge form data into document
      s.save()                          # store modified document (temporary)
    else:
      page.back()
    page.end()
#---------------------------------------
  if 'do_remove' in form:
    p.log('remove request for document: %s'%st_sid)
    s=Session(bboard)
    passwd=form.getfirst('st_passwd')     # get password
    if not st_sid:
      p.log('no document selected')
      page.add_note(wb.voc['NOSEL'])
      page.back()
    else:
      if s.newsession(userid,passwd,st_sid):
        page.add(del_confirm_form(s))
        s.save()                     # store modified document (temporary)
      else:
        page.back()
    page.end()

#---------------------------------------
  if 'do_conf_remove' in form:
    p.log('remove confirmation request for document: %s'%st_sid)
    s=opensession(token)
    if s:
      removeall(arc_dir,s.doc)
      page.add_note('%s: <b>%s</b> %s' % (s.doc.st_sid,wb.voc['DOCRMVD'],wb.voc['ANDATCH']))
      s.end()
    page.end(1)
#---------------------------------------
  if 'do_canc_rem' in form:         # remove operation cancelled
    p.log("remove request cancelled")
    s=opensession(token)
    if s:
      page.add_note(wb.voc['OPCANC'])
      s.end()
    page.end(1)
#---------------------------------------
  if 'do_manut' in form:         # Maintenance operation
    passwd=form.getfirst('st_passwd')     # get password
    clean_bboard(arc_dir,userid,passwd)
    page.end(1)

#---------------------------------------
  if 'do_editini' in form:      # Write new initialization file
    text=form.getfirst('st_wbini')
    write_init(arc_dir,text)
    page.add_note(wb.voc['STCONFIG'])
    page.end(1)

#---------------------------------------
  if 'do_rembb' in form:                # Edit operation cancelled
    passwd=form.getfirst('st_passwd')     # get password
    rem_bboard(bboard,userid,passwd)
    page.end(1)

#---------------------------------------
  page.add_note(wb.voc['NOCMD'],1)
  page.end(1)

#############################################################################################
def maxsequence(arc_dir):
   docl=wb.document_list(arc_dir)
   maxval=0
   for d in docl: 
      if d['st_sequence']>maxval: maxval=d['st_sequence']
   return maxval

#############################################################################################
def show_file(bboard,document):
  fname=os.path.join(bboard,document)
  a=wb.docload(fname)

  for k in dir(a):
    attr=getattr(a,k)
    if not callable(attr):
      print "document.%s: "%k, attr

#############################################################################################


if __name__ == '__main__': mgmt_main()
