from nevow import rend, loaders, tags, inevow, url, page
from nevow.static import File
from zope.interface import implements
from pydoctor import nevowhtml, model, epydoc2stan
from pydoctor.nevowhtml import pages, summary, util
from pydoctor.astbuilder import mystr, MyTransformer
import parser

import time

def parse_str(s):
    t = parser.suite(s.strip()).totuple(1)
    return MyTransformer().get_docstring(t)


def findPageClassInDict(obj, d, default="CommonPage"):
    for c in obj.__class__.__mro__:
        n = c.__name__ + 'Page'
        if n in d:
            return d[n]
    return d[default]

class WrapperPage(rend.Page):
    def __init__(self, element):
        self.element = element
    def render_content(self, context, data):
        return self.element
    docFactory = loaders.stan(tags.directive('content'))

class PyDoctorResource(rend.ChildLookupMixin):
    implements(inevow.IResource)

    docgetter = None

    def __init__(self, system):
        self.system = system
        self.putChild('apidocs.css', File(util.templatefile('apidocs.css')))
        self.putChild('sorttable.js', File(util.templatefile('sorttable.js')))
        self.putChild('pydoctor.js', File(util.templatefile('pydoctor.js')))
        self.index = WrapperPage(self.indexPage())
        self.putChild('', self.index)
        self.putChild('index.html', self.index)
        self.putChild('moduleIndex.html',
                      WrapperPage(summary.ModuleIndexPage(self.system)))
        self.putChild('classIndex.html',
                      WrapperPage(summary.ClassIndexPage(self.system)))
        self.putChild('nameIndex.html',
                      WrapperPage(summary.NameIndexPage(self.system)))

    def indexPage(self):
        return summary.IndexPage(self.system)

    def pageClassForObject(self, ob):
        return findPageClassInDict(ob, pages.__dict__)

    def childFactory(self, ctx, name):
        if not name.endswith('.html'):
            return None
        name = name[0:-5]
        if name not in self.system.allobjects:
            return None
        obj = self.system.allobjects[name]
        return WrapperPage(self.pageClassForObject(obj)(obj, self.docgetter))

    def renderHTTP(self, ctx):
        return self.index.renderHTTP(ctx)

class IndexPage(summary.IndexPage):
    @page.renderer
    def recentChanges(self, request, tag):
        return tag

class RecentChangesPage(page.Element):
    def __init__(self, root, url):
        self.root = root
        self.url = url

    @page.renderer
    def changes(self, request, tag):
        item = tag.patternGenerator('item')
        for d in reversed(self.root.edits):
            tag[util.fillSlots(item,
                               diff=self.diff(d),
                               hist=self.hist(d),
                               object=util.taglink(d.obj),
                               time=d.time,
                               user=d.user)]
        return tag

    def diff(self, data):
        return tags.a(href=self.url.sibling(
            'diff').add(
            'ob', data.obj.fullName()).add(
            'revA', data.rev-1).add(
            'revB', data.rev))["(diff)"]

    def hist(self, data):
        return tags.a(href=self.url.sibling(
            'history').add(
            'ob', data.obj.fullName()).add(
            'rev', data.rev))["(hist)"]

    docFactory = loaders.stan(tags.html[
        tags.head[tags.title["Recent Changes"],
                  tags.link(rel="stylesheet", type="text/css", href='apidocs.css')],
        tags.body[tags.h1["Recent Changes"],
                  tags.p["See ", tags.a(href="bigDiff")["a diff containing all changes made online"]],
                  tags.ul(render=tags.directive("changes"))
                  [tags.li(pattern="item")
                   [tags.slot("diff"),
                    " - ",
                    tags.slot("hist"),
                    " - ",
                    tags.slot("object"),
                    " - ",
                    tags.slot("time"),
                    " - ",
                    tags.slot("user"),
                    ]]]])

class EditableDocGetter(object):
    def __init__(self, root):
        self.root = root

    def get(self, ob, summary=False):
        return self.root.stanForOb(ob, summary=summary)

def userIP(req):
    # obviously this is at least slightly a guess.
    xff = req.received_headers.get('x-forwarded-for')
    if xff:
        return xff
    else:
        return req.getClientIP()

class ErrorPage(rend.Page):
    docFactory = loaders.stan(tags.html[
        tags.head[tags.title["Error"]],
        tags.body[tags.p["An error occurred."]]])


def origstring(ob, lines=None):
    if lines:
        firstline = lines[ob.docstring.linenumber - len(ob.docstring.orig.splitlines())]
        indent = (len(firstline) - len(firstline.lstrip()))*' '
    else:
        indent = ''
    return indent + ob.docstring.orig

class EditPage(rend.Page):
    def __init__(self, root, ob, origob, docstring=None):
        self.root = root
        self.ob = ob
        self.origob = origob
        self.docstring = docstring
        self.lines = open(self.ob.parentMod.filepath, 'rU').readlines()

    def render_title(self, context, data):
        return context.tag[u"Editing docstring of \N{LEFT DOUBLE QUOTATION MARK}",
                           self.ob.fullName(),
                           u"\N{RIGHT DOUBLE QUOTATION MARK}"]
    def render_preview(self, context, data):
        if self.docstring is not None:
            docstring = parse_str(self.docstring)
            return context.tag[epydoc2stan.doc2html(self.ob, docstring=docstring),
                               tags.h2["Edit"]]
        else:
            return ()
    def render_value(self, context, data):
        return self.ob.fullName()
    def render_before(self, context, data):
        lineno = self.ob.linenumber
        firstlineno = max(0, lineno-6)
        lines = self.lines[firstlineno:lineno]
        if not lines:
            return ()
        if lineno > 0:
            lines.insert(0, '...\n')
        return context.tag[lines]
    def render_rows(self, context, data):
        docstring = context.arg('docstring', origstring(self.ob, self.lines))
        if docstring is None:
            docstring = ''
        return len(docstring.splitlines())
    def render_textarea(self, context, data):
        docstring = context.arg('docstring', origstring(self.ob, self.lines))
        if docstring is None:
            docstring = ''
        return context.tag[docstring]
    def render_after(self, context, data):
        lineno = self.ob.linenumber + len(self.ob.docstring.orig.splitlines())
        lastlineno = lineno + 6
        alllines = open(self.ob.parentMod.filepath, 'rU').readlines()
        lines = alllines[lineno:lastlineno]
        if not lines:
            return ()
        if lastlineno < len(alllines):
            lines.append('...\n')
        return context.tag[lines]
    def render_url(self, context, data):
        return 'edit?ob=' + self.ob.fullName()

    docFactory = loaders.xmlfile(util.templatefile("edit.html"))

class HistoryPage(rend.Page):
    def __init__(self, root, ob, origob, rev):
        self.root = root
        self.ob = ob
        self.origob = origob
        self.rev = rev

    def render_title(self, context, data):
        return context.tag[u"History of \N{LEFT DOUBLE QUOTATION MARK}" +
                           self.ob.fullName() +
                           u"\N{RIGHT DOUBLE QUOTATION MARK}s docstring"]
    def render_links(self, context, data):
        ds = self.root.editsbyob[self.ob]
        therange = range(len(ds))
        rev = therange[self.rev]
        ul = tags.ul()
        for i in therange:
            li = tags.li()
            if i:
                li[tags.a(href=url.URL.fromContext(context).sibling(
                    'diff').add(
                    'ob', self.origob.fullName()).add(
                    'revA', i-1).add(
                    'revB', i))["(diff)"]]
            else:
                li["(diff)"]
            li[" - "]
            if i == len(ds) - 1:
                label = "Latest"
            else:
                label = str(i)
            if i == rev:
                li[label]
            else:
                li[tags.a(href=url.gethere.replace('rev', str(i)))[label]]
            li[' - ' + ds[i].user + '/' + ds[i].time]
            ul[li]
        return context.tag[ul]
    def render_docstring(self, context, data):
        docstring = self.root.editsbyob[self.ob][self.rev].newDocstring
        if docstring is None:
            docstring = ''
        return epydoc2stan.doc2html(self.ob, docstring=docstring)
    def render_linkback(self, context, data):
        return util.taglink(self.ob, label="Back")

    docFactory = loaders.stan(tags.html[
        tags.head[tags.title(render=tags.directive('title')),
                  tags.link(rel="stylesheet", type="text/css", href='apidocs.css')],
        tags.body[tags.h1(render=tags.directive('title')),
                  tags.p(render=tags.directive('links')),
                  tags.div(render=tags.directive('docstring')),
                  tags.p(render=tags.directive('linkback'))]])


class Edit(object):
    def __init__(self, obj, rev, newDocstring, user, time):
        self.obj = obj
        self.rev = rev
        self.newDocstring = newDocstring
        self.user = user
        self.time = time

def filepath(ob):
    mod = ob.parentMod
    filepath = mod.filepath
    while mod:
        top = mod
        mod = mod.parent
    toppath = top.contents['__init__'].filepath[:-(len('__init__.py') + 1 + len(top.name))]
    return filepath[len(toppath):]

class FileDiff(object):
    def __init__(self, ob):
        self.ob = ob
        self.lines = [l[:-1] for l in open(ob.filepath, 'rU').readlines()]
        self.orig_lines = self.lines[:]
        self.delta = 0

    def reset(self):
        self.orig_lines = self.lines[:]
        self.delta = 0

    def apply_edit(self, editA, editB):
        if not editA.newDocstring:
            lineno = editA.obj.linenumber + 1
            origlines = []
        else:
            origlines = editA.newDocstring.orig.splitlines()
            lineno = editA.newDocstring.linenumber - len(origlines)
        firstdocline = lineno + self.delta
        lastdocline = firstdocline + len(origlines)
        if editB.newDocstring:
            newlines = editB.newDocstring.orig.splitlines()
        else:
            newlines = []
        self.lines[firstdocline:lastdocline] = newlines
        self.delta += len(origlines) - len(newlines)

    def diff(self):
        orig = [line + '\n' for line in self.orig_lines]
        new = [line + '\n' for line in self.lines]
        import difflib
        fpath = filepath(self.ob)
        return ''.join(difflib.unified_diff(orig, new,
                                            fromfile=fpath,
                                            tofile=fpath))


class DiffPage(rend.Page):
    def __init__(self, root, ob, origob, editA, editB):
        self.root = root
        self.ob = ob
        self.origob = origob
        self.editA = editA
        self.editB = editB

    def render_title(self, context, data):
        return context.tag["Viewing differences between revisions ",
                           self.editA.rev, " and ", self.editB.rev, " of ",
                           u"\N{LEFT DOUBLE QUOTATION MARK}" +
                           self.origob.fullName() + u"\N{RIGHT DOUBLE QUOTATION MARK}"]

    def render_diff(self, context, data):
        fd = FileDiff(self.ob.parentMod)
        fd.apply_edit(self.root.editsbyob[self.ob][0], self.editA)
        fd.reset()
        fd.apply_edit(self.editA, self.editB)
        return tags.pre[fd.diff()]

    docFactory = loaders.xmlfile(util.templatefile('diff.html'))

class BigDiffPage(rend.Page):
    def __init__(self, system, root):
        self.system = system
        self.root = root

    def render_bigDiff(self, context, data):
        mods = {}
        for e in self.root.edits:
            m = e.obj.parentMod
            if m not in mods:
                mods[m] = FileDiff(m)
            i = e.obj.edits.index(e)
            mods[m].apply_edit(e.obj.edits[i-1], e.obj.edits[i])
        r = []
        for mod in sorted(mods, key=lambda x:x.filepath):
            r.append(tags.pre[mods[mod].diff()])
        return r

    docFactory = loaders.xmlfile(util.templatefile('bigDiff.html'))


def absoluteURL(ctx, ob):
    if ob.document_in_parent_page:
        p = self.origob.parent
        if isinstance(p, model.Module) and p.name == '__init__':
            p = p.parent
        child = p.fullName() + '.html'
        frag = ob.name
    else:
        child = ob.fullName() + '.html'
        frag = None
    return str(url.URL.fromContext(ctx).clear().sibling(child).anchor(frag))

class EditingPyDoctorResource(PyDoctorResource):
    def __init__(self, system):
        PyDoctorResource.__init__(self, system)
        self.edits = []
        self.editsbyob = {}
        self.editsbymod = {}
        self.docgetter = EditableDocGetter(self)

    def indexPage(self):
        return IndexPage(self.system)

    def child_recentChanges(self, ctx):
        return WrapperPage(RecentChangesPage(self, url.URL.fromContext(ctx)))

    def child_edit(self, ctx):
        origob = ob = self.system.allobjects.get(ctx.arg('ob'))
        if ob is None:
            return ErrorPage()
        if isinstance(ob, model.Package):
            ob = ob.contents['__init__']
        newDocstring = ctx.arg('docstring', None)
        action = ctx.arg('action', 'Preview')
        if action in ('Submit', 'Cancel'):
            req = ctx.locate(inevow.IRequest)
            if action == 'Submit':
                self.newDocstring(userIP(req), ob, origob, newDocstring)
            req.redirect(absoluteURL(ctx, ob))
            return ''
        return EditPage(self, ob, origob, newDocstring)

    def child_history(self, ctx):
        try:
            rev = int(ctx.arg('rev', '-1'))
        except ValueError:
            return ErrorPage()
        try:
            origob = ob = self.system.allobjects[ctx.arg('ob')]
        except KeyError:
            return ErrorPage()
        if isinstance(ob, model.Package):
            ob = ob.contents['__init__']
        try:
            self.editsbyob[ob][rev]
        except (IndexError, KeyError):
            return ErrorPage()
        return HistoryPage(self, ob, origob, rev)

    def child_diff(self, ctx):
        origob = ob = self.system.allobjects.get(ctx.arg('ob'))
        if ob is None:
            return ErrorPage()
        if isinstance(ob, model.Package):
            ob = ob.contents['__init__']
        try:
            revA = int(ctx.arg('revA', ''))
            revB = int(ctx.arg('revB', ''))
        except ValueError:
            return ErrorPage()
        try:
            edits = self.editsbyob[ob]
        except KeyError:
            return ErrorPage()
        try:
            editA = edits[revA]
            editB = edits[revB]
        except IndexError:
            return ErrorPage()
        return DiffPage(self, ob, origob, editA, editB)

    def child_bigDiff(self, ctx):
        return BigDiffPage(self.system, self)

    def currentDocstringForObject(self, ob):
        for source in ob.docsources():
            if source in self.editsbyob:
                d = self.editsbyob[source][-1].newDocstring
            else:
                d = source.docstring
            if d is not None:
                return d
        return ''

    def addEdit(self, edit):
        self.editsbyob.setdefault(edit.obj, []).append(edit)
        self.editsbymod.setdefault(edit.obj.parentMod, []).append(edit)
        self.edits.append(edit)

    def newDocstring(self, user, ob, origob, newDocstring):
        if ob not in self.editsbyob:
            self.editsbyob[ob] = [Edit(origob, 0, ob.docstring, 'no-one', 'Dawn of time')]
        if ob.parentMod not in self.editsbymod:
            self.editsbymod[ob.parentMod] = []

        if not newDocstring:
            newDocstring = None
        else:
            newDocstring = parse_str(newDocstring)
            orig = origstring(ob)
            if orig:
                l = len(orig.splitlines())
                newDocstring.linenumber = ob.docstring.linenumber - l + len(newDocstring.orig.splitlines())
            else:
                newDocstring.linenumber = ob.linenumber + 1 + len(newDocstring.orig.splitlines())

        edit = Edit(origob, len(self.editsbyob[ob]), newDocstring, user,
                    time.strftime("%Y-%m-%d %H:%M:%S"))
        self.addEdit(edit)

    def stanForOb(self, ob, summary=False):
        if summary:
            return epydoc2stan.doc2html(ob, summary=True, docstring=self.currentDocstringForObject(ob))
        origob = ob
        if isinstance(ob, model.Package):
            ob = ob.contents['__init__']
        r = [tags.div[epydoc2stan.doc2html(ob, docstring=self.currentDocstringForObject(ob))],
             tags.a(href="edit?ob="+origob.fullName())["Edit"],
             " "]
        if ob in self.editsbyob:
            r.append(tags.a(href="history?ob="+origob.fullName())["View docstring history (",
                                                                  len(self.editsbyob[ob]),
                                                                  " versions)"])
        else:
            r.append(tags.span(class_='undocumented')["No edits yet."])
        return r


def resourceForPickleFile(pickleFilePath, configFilePath=None):
    import cPickle
    system = cPickle.load(open(pickleFilePath, 'rb'))
    from pydoctor.driver import getparser, readConfigFile
    if configFilePath is not None:
        system.options, _ = getparser().parse_args(['-c', configFilePath])
        readConfigFile(system.options)
    else:
        system.options, _ = getparser().parse_args([])
    return EditingPyDoctorResource(system)
