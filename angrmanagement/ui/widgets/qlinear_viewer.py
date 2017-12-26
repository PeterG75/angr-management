
import logging

from PySide.QtGui import QWidget, QHBoxLayout, QPainter
from PySide.QtCore import Qt
from bintrees import AVLTree

from angr.block import Block
from angr.analyses.cfg.cfb import Unmapped

from ...config import Conf
from .qgraph import QBaseGraph
from .qblock import QBlock
from .qunmapped_block import QUnmappedBlock

_l = logging.getLogger('ui.widgets.qlinear_viewer')


class QLinearGraphicsView(QBaseGraph):
    def __init__(self, viewer, disasm_view, parent=None):
        super(QLinearGraphicsView, self).__init__(viewer.workspace, parent)

        self.viewer = viewer
        self.disasm_view = disasm_view

        self.key_released.connect(self._on_keyreleased_event)

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.horizontalScrollBar().setSingleStep(Conf.disasm_font_height)
        self.verticalScrollBar().setSingleStep(1)

    #
    # Events
    #

    def _on_keyreleased_event(self, key_event):

        key = key_event.key()
        if key == Qt.Key_Space:
            self.disasm_view.display_disasm_graph()
            return True

        return False

    def resizeEvent(self, event):

        self._update_size()

    def paintEvent(self, event):
        """
        Paint the linear view.

        :param event:
        :return:
        """

        painter = QPainter(self.viewport())
        self._paint_objects(painter)

    #
    # Public methods
    #

    def refresh(self):

        self._update()
        self.viewport().update()

    def request_relayout(self):
        pass

    #
    # Private methods
    #

    def _paint_objects(self, painter):

        new_offset = self.verticalScrollBar().value()

        self.viewer.prepare_objects(new_offset)

        x = 80
        y = self.viewer.paint_start_offset - self.viewer.offset

        for obj in self.viewer.objects:
            obj.x = x
            obj.y = y
            obj.paint(painter)

            y += obj.height

    def _update(self):
        self.verticalScrollBar().setRange(0, self.viewer.max_offset - self.height() / 2)
        self.verticalScrollBar().setValue(self.viewer.offset)
        # TODO: horizontalScrollbar().setRange()

        self._update_size()


class QLinearViewer(QWidget):
    def __init__(self, workspace, disasm_view, parent=None):
        super(QLinearViewer, self).__init__(parent)

        self.workspace = workspace
        self.disasm_view = disasm_view

        self.objects = [ ]  # Objects that will be painted

        self.cfg = None
        self.cfb = None
        self._offset_to_addr = AVLTree()
        self._addr_to_offset = AVLTree()
        self._offset_to_object = AVLTree()
        self._offset = 0
        self._paint_start_offset = 0

        self._linear_view = None  # type: QLinearGraphicsView
        self._disasms = { }

        self._init_widgets()

    #
    # Properties
    #

    @property
    def offset(self):
        return self._offset

    @offset.setter
    def offset(self, v):
        self._offset = v

    @property
    def paint_start_offset(self):
        return self._paint_start_offset

    @property
    def max_offset(self):

        # TODO: Cache it

        try:
            max_off, obj = self._offset_to_object.max_item()
        except (KeyError, ValueError):
            return 0

        return max_off + obj.height


    #
    # Public methods
    #

    def initialize(self):
        self._make_objects()

    def navigate_to_addr(self, addr):
        if not self._addr_to_offset:
            return
        try:
            _, floor_offset = self._addr_to_offset.floor_item(addr)
        except KeyError:
            _, floor_offset = floor_offset = self._addr_to_offset.min_item()
        self.navigate_to(floor_offset)

    def refresh(self):
        self._linear_view.refresh()

    def navigate_to(self, offset):

        self._linear_view.verticalScrollBar().setValue(int(offset))

        self.prepare_objects(offset)

        self._linear_view.refresh()

    def prepare_objects(self, offset):

        if offset == self._offset:
            return

        try:
            start_offset = self._offset_to_object.floor_key(offset)
        except (KeyError, ValueError):
            try:
                start_offset = self._offset_to_object.min_key()
            except ValueError:
                # Tree is empty
                return

        # Update offset
        self._offset = offset
        self._paint_start_offset = start_offset

        self.objects = [ ]
        max_height = self.height()

        for off, obj in self._offset_to_object.iter_items(start_key=start_offset):
            self.objects.append(obj)
            if off - offset > max_height:
                break

    #
    # Private methods
    #

    def _init_widgets(self):

        self._linear_view = QLinearGraphicsView(self, self.disasm_view)

        layout = QHBoxLayout()
        layout.addWidget(self._linear_view)
        layout.setContentsMargins(0, 0, 0, 0)

        self.setLayout(layout)

    def _make_objects(self):

        self._addr_to_offset.clear()
        self._offset_to_addr.clear()
        self._offset_to_object.clear()

        y = 0

        for obj_addr, obj in self.cfb.floor_items():

            if isinstance(obj, Block):
                func_addr = self.cfg.get_any_node(obj.addr).function_address  # FIXME: Resiliency
                func = self.cfg.kb.functions[func_addr]  # FIXME: Resiliency
                disasm = self._get_disasm(func)
                qobject = QBlock(self.workspace, func_addr, self.disasm_view, disasm,
                                 self.disasm_view._flow_graph.infodock, obj.addr, [ obj ], { }, mode='linear',
                                 )

            elif isinstance(obj, Unmapped):
                qobject = QUnmappedBlock(self.workspace, obj_addr)

            else:
                continue

            self._offset_to_object[y] = qobject
            if obj_addr not in self._addr_to_offset:
                self._addr_to_offset[obj_addr] = y
            y += qobject.height

    def _get_disasm(self, func):
        """

        :param func:
        :return:
        """

        if func.addr not in self._disasms:
            self._disasms[func.addr] = self.workspace.instance.project.analyses.Disassembly(function=func)
        return self._disasms[func.addr]
