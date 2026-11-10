"""Human-readable relationship correction before saving."""
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QComboBox,QPushButton,QDialogButtonBox,QAbstractItemView
from core.extractor import _INVERSE_RELATIONS

class RelationsDialog(QDialog):
    def __init__(self,concept,titles,parent=None):
        super().__init__(parent)
        self.concept=concept
        self.titles=sorted(set(titles+[r['target'] for r in concept.relations])-{concept.title})
        self.setWindowTitle('修改知识联系 · '+concept.title)
        self.resize(860,480)
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel('选择目标、关系与依据。也可以输入尚未创建的笔记标题；双向联系会一起更新。'))
        self.table=QTableWidget(0,3)
        self.table.setHorizontalHeaderLabels(['目标笔记','关系','说明'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setColumnWidth(0,235)
        self.table.setColumnWidth(1,125)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table,1)
        for relation in concept.relations:self.add_row(relation)
        row=QHBoxLayout()
        add=QPushButton('添加联系')
        add.clicked.connect(lambda:self.add_row({}))
        remove=QPushButton('删除所选联系')
        remove.clicked.connect(self.remove_rows)
        row.addWidget(add);row.addWidget(remove);row.addStretch()
        layout.addLayout(row)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def add_row(self,relation):
        row=self.table.rowCount()
        self.table.insertRow(row)
        target=QComboBox()
        target.setEditable(True)
        target.addItems(['']+self.titles)
        target.setCurrentText(relation.get('target',''))
        kind=QComboBox()
        kind.addItems(list(_INVERSE_RELATIONS))
        kind.setCurrentText(relation.get('relation','相关'))
        self.table.setCellWidget(row,0,target)
        self.table.setCellWidget(row,1,kind)
        self.table.setItem(row,2,QTableWidgetItem(relation.get('reason','')))

    def remove_rows(self):
        for index in sorted({i.row() for i in self.table.selectionModel().selectedRows()},reverse=True):self.table.removeRow(index)

    def relations(self):
        relations=[]
        seen=set()
        for row in range(self.table.rowCount()):
            target=self.table.cellWidget(row,0).currentText().strip()
            kind=self.table.cellWidget(row,1).currentText()
            if not target or target==self.concept.title or (target,kind) in seen:continue
            seen.add((target,kind))
            relations.append(dict(target=target,relation=kind,reason=self.table.item(row,2).text().strip()))
        return relations
