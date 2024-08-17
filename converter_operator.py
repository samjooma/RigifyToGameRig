from doctest import FAIL_FAST
from email import header
from unittest import TestSuite
import math
import bpy
from bpy.app.handlers import persistent
from . import converter
from . import misc
from difflib import SequenceMatcher

#
# User interface classes.
#

class RIGIFY_CONVERTER_UL_ActionNameSelection(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {"DEFAULT", "COMPACT", "GRID"}:
            try:
                text = item.action.name
            except:
                text = str(None)
            layout.label(text=text)

#
# Property classes.
#

class NameProperty(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty()

class ActionProperty(bpy.types.PropertyGroup):
    action: bpy.props.PointerProperty(type=bpy.types.Action)
    frame_range_start: bpy.props.IntProperty(
        default=-1,
        name="Action start frame",
        description="Replaces the action's frame range. A negative is ignored and the action's value stays unchanged.",
    )
    frame_range_end: bpy.props.IntProperty(
        default=-1,
        name="Action end frame",
        description="Replaces the action's frame range. A negative is ignored and the action's value stays unchanged.",
    )

class RigObjectProperty(bpy.types.PropertyGroup):
    rig_object: bpy.props.PointerProperty(type=bpy.types.Object)

class RigifyConverterSceneProperties(bpy.types.PropertyGroup):
    searchable_actions: bpy.props.CollectionProperty(type=NameProperty)
    included_actions: bpy.props.CollectionProperty(type=ActionProperty)
    active_action_index: bpy.props.IntProperty()

#
# Operators.
#
class AddIncludedActionOperator(bpy.types.Operator):
    bl_idname = "rigify_converter.add_action_name"
    bl_label = "Add action name"
    bl_description = "Description"
    bl_options = {"REGISTER"}

    selected_action_name: bpy.props.StringProperty()

    def execute(self, context):
        properties = context.scene.rigify_converter
        new_action_property = properties.included_actions.add()
        new_action_property.action = bpy.data.actions[self.selected_action_name]
        return {"FINISHED"}
    
    def invoke(self, context, event):
        self.selected_action_name = ""

        properties = context.scene.rigify_converter
        properties.searchable_actions.clear()
        included_names = [x.action.name for x in properties.included_actions]
        for action in bpy.data.actions:
            if action.name not in included_names:
                searchable_action = properties.searchable_actions.add()
                searchable_action.name = action.name
        
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        properties = context.scene.rigify_converter
        layout = self.layout
        layout.prop_search(self, "selected_action_name", properties, "searchable_actions", text="")
    
class RemoveIncludedActionOperator(bpy.types.Operator):
    bl_idname = "rigify_converter.remove_action_name"
    bl_label = "Remove action name"
    bl_description = "Description"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        properties = context.scene.rigify_converter
        action_count = len(properties.included_actions)
        index = properties.active_action_index
        return action_count > 0 and index > -1 and index < action_count

    def execute(self, context):
        properties = context.scene.rigify_converter
        properties.included_actions.remove(properties.active_action_index)
        properties.active_action_index = max(0, properties.active_action_index - 1)
        return {"FINISHED"}

class RigifyConverterOperator(bpy.types.Operator):
    bl_idname = "rigify_converter.convert"
    bl_label = "Convert rigify armature"
    bl_description = "Convert selected rigify armature, its mesh, and all actions in scene"
    bl_options = {"REGISTER"}

    add_as_root_bone: bpy.props.StringProperty(
        default="root",
        name="Add as root bone",
        description="Bone that will be added to the converted rig as the root bone"
    )

    @classmethod
    def poll(cls, context):
        valid_rigs = [x for x in context.selected_objects if misc.is_valid_rig(x)]
        return len(valid_rigs) > 0

    def execute(self, context):
        properties = context.scene.rigify_converter
        for rig_object in (x for x in context.selected_objects if misc.is_valid_rig(x)):
            child_meshes = [x for x in rig_object.children if x.type == "MESH"]
            if len(child_meshes) < 1:
                self.report({"ERROR"}, "Can't convert a rig that is not the parent of any mesh.")
                return {"CANCELLED"}
            
            # If rig contains multiple meshes, only use selected rig.
            if len(child_meshes) > 1:
                child_meshes = [x for x in child_meshes if x.select_get()]
            if len(child_meshes) != 1:
                self.report({"ERROR"}, "You must select exactly one mesh to be converted when rig contains multiple meshes.")
                return {"CANCELLED"}
            
            # Check that root bone is valid.
            try:
                rig_object.data.bones[self.add_as_root_bone]
            except:
                self.report({"ERROR"}, f"Couldn't find root bone \"{self.add_as_root_bone}\" in armature \"{rig_object.name}\"")
                return {"CANCELLED"}
            
            # Modify frame ranges.
            modified_frame_ranges = {}
            for action_property in properties.included_actions:
                action = action_property.action
                new_start = action_property.frame_range_start
                new_end = action_property.frame_range_end

                frame_range = (math.floor(action.frame_range[0]), math.ceil(action.frame_range[1]))
                modified_frame_ranges[action_property.action] = (
                    new_start if new_start > -1 else frame_range[0],
                    new_end if new_end > -1 else frame_range[1],
                )

            # Do the conversion.
            actions = [x.action for x in properties.included_actions]
            converter.convert_rigify_rig(
                context,
                rig_object,
                child_meshes[0],
                actions,
                self.add_as_root_bone,
                modified_frame_ranges,
            )
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        properties = bpy.context.scene.rigify_converter
        layout.prop(data=self, property="add_as_root_bone")
        
        actions_parent = layout.row()
        actions_list_column = actions_parent.column()
        actions_add_column = actions_parent.column(align=True)

        actions_list_column.template_list(
            listtype_name="RIGIFY_CONVERTER_UL_ActionNameSelection",
            list_id="",
            dataptr=properties,
            propname="included_actions",
            active_dataptr=properties,
            active_propname="active_action_index",
            type="DEFAULT",
        )

        actions_add_column.operator(AddIncludedActionOperator.bl_idname, text="", icon="ADD")
        actions_add_column.operator(RemoveIncludedActionOperator.bl_idname, text="", icon="REMOVE")

#
# Registration.
#

def menu_func(self, context):
    self.layout.operator(RigifyConverterOperator.bl_idname, text=RigifyConverterOperator.bl_label)

classes = (
    RIGIFY_CONVERTER_UL_ActionNameSelection,
    NameProperty,
    ActionProperty,
    RigObjectProperty,
    RigifyConverterSceneProperties,
    AddIncludedActionOperator,
    RemoveIncludedActionOperator,
    RigifyConverterOperator,
)

def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.rigify_converter = bpy.props.PointerProperty(type = RigifyConverterSceneProperties)
    bpy.types.VIEW3D_MT_object_convert.append(menu_func)
    
def unregister():
    for c in classes:
        bpy.utils.unregister_class(c)
    del bpy.types.Scene.rigify_converter
    bpy.types.VIEW3D_MT_object_convert.remove(menu_func)
    