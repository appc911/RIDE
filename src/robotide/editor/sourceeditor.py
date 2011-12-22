import wx
from wx import stc
from StringIO import StringIO
from robot.parsing.model import TestDataDirectory
from robot.parsing.populators import FromFilePopulator
from robot.parsing.txtreader import TxtReader
from robotide.publish.messages import RideMessage, RideOpenSuite, RideDataChangedToDirty

from robotide.widgets import VerticalSizer
from robotide.pluginapi import (Plugin, ActionInfo, RideSaving,
        TreeAwarePluginMixin, RideTreeSelection, RideNotebookTabChanging)


class SourceEditorPlugin(Plugin, TreeAwarePluginMixin):
    title = 'Txt Edit'

    def __init__(self, application):
        Plugin.__init__(self, application)
        self._editor_component = None

    @property
    def _editor(self):
        if not self._editor_component:
            self._editor_component = SourceEditor(self.notebook, self.title)
        return self._editor_component

    def enable(self):
        self.register_action(ActionInfo('Edit', 'Edit Source', self.OnOpen))
        self.add_self_as_tree_aware_plugin()
        self.subscribe(self.OnSaving, RideSaving)
        self.subscribe(self.OnTreeSelection, RideTreeSelection)
        self.subscribe(self.OnTreeSelection, RideMessage)
        self.subscribe(self.OnTabChange, RideNotebookTabChanging)
        self._open()

    def disable(self):
        self.unsubscribe_all()
        self.remove_self_from_tree_aware_plugins()
        self.unregister_actions()
        self._editor_component = None

    def OnOpen(self, event):
        self._open()

    def _open(self):
        self._open_data_in_editor()
        self.show_tab(self._editor)

    def OnSaving(self, message):
        if self.is_focused():
            self._editor.save()
            self.tree.refresh_current_datafile()

    def OnTreeSelection(self, message):
        if isinstance(message, RideDataChangedToDirty):
            return
        if self.is_focused():
            if isinstance(message, RideOpenSuite):
                self._editor.reset()
            if self._editor.dirty:
                self._ask_and_apply()
            self._open_data_in_editor()

    def _open_data_in_editor(self):
        datafile_controller = self.tree.get_selected_datafile_controller()
        if datafile_controller:
            data = DataFileWrapper(datafile_controller)
            self._editor.open(data)

    def OnTabChange(self, message):
        if message.newtab == self.title:
            self._open()
        if message.oldtab == self.title:
            if self._editor.dirty:
                self._ask_and_apply()

    def _ask_and_apply(self):
        # TODO: use widgets.Dialog
        ret = wx.MessageDialog(self._editor, 'Apply changes?', 'Source changed',
                               style=wx.YES_NO | wx.ICON_QUESTION).ShowModal()
        if ret == wx.ID_YES:
            self._editor.save()
            self.tree.refresh_current_datafile()
        self._editor.reset()

    def is_focused(self):
        return self.notebook.current_page_title == self.title


class DataFileWrapper(object): # TODO: bad class name

    def __init__(self, data):
        self._data = data

    def update_from(self, content):
        src = StringIO(content)
        target = self._create_target()
        FromStringIOPopulator(target).populate(src)
        self._sanity_check(target, content)
        self._data.set_datafile(target)
        self.mark_data_dirty()

    def _sanity_check(self, candidate, current):
        candidate_txt = self._txt_data(candidate)
        current_none_empty_lines = self._none_empty_lines(current)
        candidate_none_empty_lines = self._none_empty_lines(candidate_txt)
        if current_none_empty_lines > candidate_none_empty_lines:
            raise AssertionError('Sanity Check Failed')

    def _none_empty_lines(self, txt):
        return sum(1 for t in txt.splitlines() if t.strip() and not t.strip().startswith('... '))

    def mark_data_dirty(self):
        self._data.mark_dirty()

    def _create_target(self):
        target_class = type(self._data.data)
        if target_class is TestDataDirectory:
            target = TestDataDirectory(source=self._data.directory)
            target.initfile = self._data.data.initfile
            return target
        return target_class(source=self._data.source)

    @property
    def content(self):
        return self._txt_data(self._data.data)

    def _txt_data(self, data):
        output = StringIO()
        data.save(output=output, format='txt')
        return output.getvalue()


class SourceEditor(wx.Panel):

    def __init__(self, parent, title):
        wx.Panel.__init__(self, parent)
        self._parent = parent
        self.SetSizer(VerticalSizer())
        self._editor = RobotDataEditor(self)
        self.Sizer.add_expanding(self._editor)
        self._parent.AddPage(self, title)
        self._editor.Bind(wx.EVT_KEY_DOWN, self.OnEditorKey)
        self._data = None
        self._dirty = False

    @property
    def dirty(self):
        return self._dirty

    def open(self, data):
        self._data = data
        self._editor.set_text(self._data.content)

    def reset(self):
        self._dirty = False

    def save(self):
        if self.dirty:
            self._data.update_from(self._editor.utf8_text)
        self.reset()

    def OnEditorKey(self, event):
        if not self.dirty:
            self._mark_file_dirty()
        event.Skip()

    def _mark_file_dirty(self):
        self._dirty = True
        self._data.mark_data_dirty()


class RobotDataEditor(stc.StyledTextCtrl):

    def __init__(self, parent):
        stc.StyledTextCtrl.__init__(self, parent)
        self.StyleSetSpec(stc.STC_STYLE_DEFAULT, 'fore:#000000,back:#FFFFFF,face:MonoSpace,size:9')

    def set_text(self, text):
        self.SetText(text)

    @property
    def utf8_text(self):
        return self.GetText().encode('UTF-8')


class FromStringIOPopulator(FromFilePopulator):

    def populate(self, content):
        TxtReader().read(content, self)
