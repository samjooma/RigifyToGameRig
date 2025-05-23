import bpy
from bpy.app.handlers import persistent
from . import duplicator
from . import misc

#
# Operators.
#

class RigifyDuplicatorOperator(bpy.types.Operator):
    bl_idname = "rigify_duplication.duplicate"
    bl_label = "Create simple Rigify duplicate"
    bl_description = "Create a simplified duplicate of a Rigify armature and make the new armature follow the transformations of the original"
    bl_options = {"REGISTER"}

    name_suffix: bpy.props.StringProperty(
        default="_Converted", name="Name suffix", description="Suffix to add to the name of the new object. Any object with the same name is overwritten"
    )

    @classmethod
    def poll(cls, context):
        if context.mode != "OBJECT":
            return False

        valid_rigs = [
            x for x in context.selected_objects if
            misc.is_valid_rig(context, x) and
            any(child.type == "MESH" for child in x.children) and
            x.data.get("rig_id") is not None
        ]
        return len(valid_rigs) >= 1

    def execute(self, context):
        # rig_id is a custom property generated by rigify, use it to detect rigify rigs.
        valid_rigs = [
            x for x in context.selected_objects if
            misc.is_valid_rig(context, x) and
            any(child.type == "MESH" for child in x.children) and
            x.data.get("rig_id") is not None
        ]

        for rig_object in valid_rigs:
            # Do the conversion.
            created_rig = duplicator.convert_rigify_rig(
                context,
                rig_object,
                self.name_suffix
            )

            # Remove DEF prefix.
            for bone in created_rig.data.bones:
                if bone.name.startswith("DEF-"):
                    bone.name = misc.replace_prefix(bone.name, "DEF-", "")
            
            # Rename root.
            root_bone_candidates = [x for x in created_rig.data.bones if (x.parent is None or x.parent == "")]
            if len(root_bone_candidates) != 1:
                self.report({"ERROR"}, f"Couldn't find root bone in converted rig \"{created_rig.name}\"")
                return {"CANCELLED"}
            root_bone_candidates[0].name = "root"

        return {"FINISHED"}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

#
# Registration.
#

def menu_func(self, context):
    self.layout.operator(RigifyDuplicatorOperator.bl_idname, text=RigifyDuplicatorOperator.bl_label)

classes = (
    RigifyDuplicatorOperator,
)

def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.VIEW3D_MT_add.append(menu_func)
    
def unregister():
    for c in classes:
        bpy.utils.unregister_class(c)
    bpy.types.VIEW3D_MT_add.remove(menu_func)
    