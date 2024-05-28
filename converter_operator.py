from doctest import FAIL_FAST
from email import header
from unittest import TestSuite
import bpy
from bpy.app.handlers import persistent
from . import converter
from . import misc
from difflib import SequenceMatcher

@persistent
def depsgraph_update_handler(scene):
    # Add selected rigs to addon properties.
    bpy.context.scene.rigify_converter.rigs_to_convert.clear()
    for rig_object in (x for x in bpy.context.selected_objects if misc.is_valid_rig(x) and misc.is_rigify_rig(x)):
        rig_property = bpy.context.scene.rigify_converter.rigs_to_convert.add()
        rig_property.rig_object = rig_object

#
# Property classes.
#

class RigObjectProperty(bpy.types.PropertyGroup):
    rig_object: bpy.props.PointerProperty(type = bpy.types.Object)

class RigifyConverterProperties(bpy.types.PropertyGroup):
    rigs_to_convert: bpy.props.CollectionProperty(type = RigObjectProperty)

#
# Operators.
#

class RigifyConverterOperator(bpy.types.Operator):
    bl_idname = "object.rigify_converter"
    bl_label = "Convert rigify armature"
    bl_description = "Convert selected rigify armature, its mesh, and all actions in scene"
    bl_options = {"REGISTER"}

    add_as_root_bone : bpy.props.StringProperty(
        default="root",
        name="Add as root bone",
        description="Bone that will be added to the converted rig as the root bone"
    )

    @classmethod
    def poll(cls, context):
        if len(context.scene.rigify_converter.rigs_to_convert) <= 0: return False
        for rig_object in (x.rig_object for x in context.scene.rigify_converter.rigs_to_convert):
            if not misc.is_valid_rig(rig_object): return False
            if not misc.is_rigify_rig(rig_object): return False
        return True

    def execute(self, context):
        for rig_object in (x.rig_object for x in bpy.context.scene.rigify_converter.rigs_to_convert):
            child_meshes = [x for x in rig_object.children if x.type == "MESH"]
            if len(child_meshes) > 1:
                self.report({"ERROR"}, "Can't convert a rig that is the parent of multiple meshes.")
                return {"CANCELLED"}
            if len(child_meshes) < 1:
                self.report({"ERROR"}, "Can't convert a rig that is not the parent of any mesh.")
                return {"CANCELLED"}
            converter.convert_rigify_rig(rig_object, child_meshes[0], [x for x in bpy.data.actions], self.add_as_root_bone)
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

#
# Registration.
#

def menu_func(self, context):
    self.layout.operator(RigifyConverterOperator.bl_idname, text=RigifyConverterOperator.bl_label)

classes = (
    RigObjectProperty,
    RigifyConverterProperties,
    RigifyConverterOperator,
)

def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.rigify_converter = bpy.props.PointerProperty(type = RigifyConverterProperties)
    bpy.app.handlers.depsgraph_update_post.append(depsgraph_update_handler)
    bpy.types.VIEW3D_MT_object_convert.append(menu_func)
    
def unregister():
    for c in classes:
        bpy.utils.unregister_class(c)
    del bpy.types.Scene.rigify_converter
    bpy.app.handlers.depsgraph_update_post.remove(depsgraph_update_handler)
    bpy.types.VIEW3D_MT_object_convert.remove(menu_func)
    