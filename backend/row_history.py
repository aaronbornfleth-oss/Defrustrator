"""Reversible row transactions; original PDF data and hardware stay untouched."""
from copy import deepcopy
from dataclasses import dataclass


@dataclass
class Change:
    label: str
    before: dict
    after: dict
    before_rows: list | None = None
    after_rows: list | None = None


class RowHistory:
    def __init__(self, report):
        self.report = report
        self.undo_stack = []
        self.redo_stack = []
        self.mark_saved()

    def mark_saved(self):
        self.saved_items = deepcopy(self.report.items)

    def original_items(self):
        """Align imported baselines with current rows, including every split child.

        History is persisted in .mddorder files, so this also works for older
        saved orders without rereading the PDF or changing the file format.
        """
        key = tuple(id(change) for change in self.undo_stack)
        if getattr(self, '_original_key', None) == key:
            return self._original_rows
        rows = list(self.report.items)
        for change in reversed(self.undo_stack):
            if change.before_rows is not None:
                rows = list(change.before_rows)
            else:
                for index, item in change.before.items():
                    rows[index] = item
        for change in self.undo_stack:
            if change.before_rows is not None:
                index = next(iter(change.before))
                count = len(change.after_rows) - len(change.before_rows) + 1
                rows[index:index + 1] = [rows[index]] * count
        self._original_key, self._original_rows = key, rows
        return rows

    @property
    def dirty(self):
        return self.report.items != self.saved_items

    def apply(self, updates, label):
        updates = {i: item for i, item in updates.items() if item != self.report.items[i]}
        if not updates:
            return False
        change = Change(label, deepcopy({i: self.report.items[i] for i in updates}), deepcopy(updates))
        self._restore(change.after)
        self.undo_stack.append(change)
        self.redo_stack.clear()
        return True

    def _restore(self, rows):
        for index, item in rows.items():
            self.report.items[index] = deepcopy(item)

    def replace_row(self, index, rows, label):
        """Insert split rows adjacent to their source as one undoable change."""
        if not rows:
            raise ValueError('A row replacement must contain at least one row.')
        if len(rows) == 1:
            return self.apply({index: rows[0]}, label)
        if any(row.qty != 1 for row in rows[:-1]):
            raise ValueError('Split doors must have quantity 1.')
        before = deepcopy(self.report.items)
        after = deepcopy(before)
        after[index:index + 1] = deepcopy(rows)
        change = Change(label, {index: deepcopy(before[index])}, {index: deepcopy(rows[0])}, before, after)
        self.report.items[:] = deepcopy(after)
        self.undo_stack.append(change)
        self.redo_stack.clear()
        return True

    def _restore_change(self, change, after=False):
        snapshot = change.after_rows if after else change.before_rows
        if snapshot is not None:
            self.report.items[:] = deepcopy(snapshot)
        else:
            self._restore(change.after if after else change.before)

    def undo(self):
        if not self.undo_stack:
            return None
        change = self.undo_stack.pop()
        self._restore_change(change)
        self.redo_stack.append(change)
        return change

    def redo(self):
        if not self.redo_stack:
            return None
        change = self.redo_stack.pop()
        self._restore_change(change, after=True)
        self.undo_stack.append(change)
        return change


def bind_undo_redo(window, undo, redo):
    # Bind per window so an editor never undoes a different, committed row.
    for key in ('<Control-z>', '<Control-Z>'):
        window.bind(key, lambda _event: (undo(), 'break')[1])
    for key in ('<Control-y>', '<Control-Y>', '<Control-Shift-z>', '<Control-Shift-Z>'):
        window.bind(key, lambda _event: (redo(), 'break')[1])


def bind_row_delete(tree, delete_rows):
    # Scope Delete to the table. In an editor it must still delete text.
    def delete_key(_event):
        delete_rows()
        return 'break'
    for key in ('<Delete>', '<KP_Delete>'):
        tree.bind(key, delete_key)


class DraftHistory:
    """Snapshot a whole form after one UI event, including linked defaults."""
    def __init__(self, window, variables, capture, restore):
        self.window, self.capture, self.restore = window, capture, restore
        self.undo_stack, self.redo_stack = [], []
        self.current = deepcopy(capture())
        self.pending = None
        self.restoring = False
        for variable in variables:
            variable.trace_add('write', self.schedule)
        bind_undo_redo(window, self.undo, self.redo)
        window.bind('<Destroy>', lambda event: self.cancel_pending() if event.widget is window else None, add='+')

    def schedule(self, *_args):
        if not self.restoring and self.pending is None:
            self.pending = self.window.after_idle(self.flush)

    def cancel_pending(self):
        if self.pending is not None:
            self.window.after_cancel(self.pending)
            self.pending = None

    def flush(self):
        self.cancel_pending()
        state = deepcopy(self.capture())
        if state != self.current:
            self.undo_stack.append(self.current)
            self.current = state
            self.redo_stack.clear()

    def step(self, source, destination):
        self.flush()
        if not source:
            return
        destination.append(self.current)
        self.current = source.pop()
        self.restoring = True
        try:
            self.restore(deepcopy(self.current))
        finally:
            self.restoring = False

    def undo(self):
        self.step(self.undo_stack, self.redo_stack)

    def redo(self):
        self.step(self.redo_stack, self.undo_stack)
