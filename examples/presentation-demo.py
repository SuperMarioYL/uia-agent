from types import SimpleNamespace
from uia_agent.uia_tree import snapshot_from,count_nodes
class Control:
 def __init__(self,role,name='',children=(),actionable=False):
  self.ControlTypeName=role+'Control';self.Name=name;self._children=children;self.actionable=actionable
  self.BoundingRectangle=SimpleNamespace(left=0,top=0,right=100,bottom=50)
 def GetChildren(self):return self._children
 def GetInvokePattern(self):return object() if self.actionable else None
root=Control('Window','Demo',[Control('Pane'),Control('Button','Save',actionable=True)])
frame=snapshot_from(root)
print('input nodes: 3')
print('retained nodes:',count_nodes(frame))
for child in frame.children:print('retained:',child.role,child.name,child.patterns)
print('stable snapshot IDs:',frame.model_dump()==snapshot_from(root).model_dump())
