"""Prototype-only multicolumn checklist adapter; no changes to the KRT panel."""
import wx
import wx.dataview as dv


class BranchScopeList(dv.DataViewListCtrl):
    def __init__(self, panel, scope_label, on_preview, on_check):
        super().__init__(panel, size=panel.FromDIP((223, 180)),
                         style=dv.DV_MULTIPLE | dv.DV_ROW_LINES | dv.DV_VERT_RULES)
        self._scope_label = scope_label
        self._silent = False
        self._scope_width = self.FromDIP(50)
        self._resize_pending = False
        self._net_width = self.FromDIP(120)
        check_column = self.AppendToggleColumn('', width=self.FromDIP(32))
        check_column.SetMinWidth(self.FromDIP(24))
        check_column.SetWidth(self.FromDIP(32))
        self.AppendTextColumn('Net', width=self._net_width)
        scope_column = self.AppendTextColumn('EB', width=self.FromDIP(50))
        scope_column.SetMinWidth(self.FromDIP(40))
        scope_column.SetWidth(self.FromDIP(50))
        self.Bind(wx.EVT_KEY_DOWN, panel._on_net_list_key)

        def preview(event):
            if not self._silent:
                on_preview(event)

        def checked(event):
            if not self._silent and event.GetColumn() == 0:
                panel._on_checklist_toggled(event)
                on_check(event)
        self.Bind(dv.EVT_DATAVIEW_SELECTION_CHANGED, preview)
        self.Bind(dv.EVT_DATAVIEW_ITEM_VALUE_CHANGED, checked)
        self.Bind(wx.EVT_SIZE, self._resize_columns)
        self.Bind(wx.EVT_SHOW, self._resize_columns)
        self.Bind(wx.EVT_MOTION, self._show_net_tooltip)

    def _show_net_tooltip(self, event):
        item, column = self.HitTest(event.GetPosition())
        text = 'EB = Elementary branches; blank = whole net.'
        if item.IsOk() and column == self.GetColumn(1):
            text = self.GetString(self.ItemToRow(item))
        if self.GetToolTipText() != text:
            self.SetToolTip(text)
        event.Skip()

    def _resize_columns(self, event=None):
        if not self:
            return
        self._apply_column_widths()
        if event is not None:
            event.Skip()
            # Native layout can adjust columns after EVT_SIZE/EVT_SHOW.
            # Reapply from the requested EB width, never its expanded width.
            if not self._resize_pending:
                self._resize_pending = True
                wx.CallAfter(self._finish_column_resize)

    def _finish_column_resize(self):
        if not self:
            return
        self._resize_pending = False
        self._apply_column_widths()

    def _apply_column_widths(self):
        remaining = self.GetClientSize().width - self.FromDIP(32) - self._scope_width
        self.GetColumn(0).SetWidth(self.FromDIP(32))
        self.GetColumn(1).SetWidth(max(self._net_width, remaining - self.FromDIP(4)))
        self.GetColumn(2).SetWidth(self._scope_width)

    def Clear(self):
        self._silent = True
        try:
            self.DeleteAllItems()
        finally:
            self._silent = False

    def Append(self, name):
        row = self.GetItemCount()
        self.AppendItem([False, name, self._scope_label(name)])
        return row

    def Check(self, row, check=True):
        self._silent = True
        try:
            self.SetToggleValue(check, row, 0)
        finally:
            self._silent = False

    def IsChecked(self, row):
        return self.GetToggleValue(row, 0)

    def GetCount(self):
        return self.GetItemCount()

    def GetString(self, row):
        return self.GetTextValue(row, 1)

    def FindString(self, name):
        return next((i for i in range(self.GetCount()) if self.GetString(i) == name), wx.NOT_FOUND)

    def GetSelections(self):
        return [self.ItemToRow(item) for item in super().GetSelections()]

    def SetSelection(self, row):
        self._silent = True
        try:
            self.SelectRow(row)
        finally:
            self._silent = False

    def Deselect(self, row):
        self._silent = True
        try:
            self.UnselectRow(row)
        finally:
            self._silent = False

    def GetCountPerPage(self):
        return max(1, self.GetClientSize().height // max(1, self.GetCharHeight() + self.FromDIP(8)))

    def SetFirstItem(self, row):
        self.EnsureVisible(self.RowToItem(row))

    def reveal_first_changed(self, names):
        """Reveal the topmost changed visible row, without selecting/checking it."""
        for row in range(self.GetCount()):
            if self.GetString(row) in names:
                self.EnsureVisible(self.RowToItem(row))
                return row
        return wx.NOT_FOUND

    def refresh_scope(self):
        widest = self.GetTextExtent('EB').width
        for row in range(self.GetCount()):
            text = self._scope_label(self.GetString(row))
            widest = max(widest, self.GetTextExtent(text).width)
            if self.GetTextValue(row, 2) != text:
                self.SetTextValue(text, row, 2)
        self._scope_width = max(self.FromDIP(50), widest + self.FromDIP(12))
        self._resize_columns()


def install(dialog):
    panel = dialog.centering_net_panel
    selected = panel.get_selected_nets()
    old = panel.net_list

    def label(name):
        branches = dialog._branch_memory.by_net.get(name, ())
        return f'{len(branches)} EB' if dialog._eb_enabled() and branches else ''

    new = BranchScopeList(panel, label, dialog._on_centering_net_row_selected,
                          dialog._on_centering_net_checked)
    new.SetToolTip(old.GetToolTipText())
    panel._list_container_sizer.Replace(old, new)
    panel._list_container_sizer.GetItem(new).SetFlag(wx.EXPAND)
    panel.net_list = new
    old.Destroy()
    panel.set_selected_nets(selected)
    dialog._clear_centering_highlight()
    panel.Layout()
