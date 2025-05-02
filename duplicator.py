from collections import defaultdict
import bpy
from . import misc

class RigConverterException(Exception):
    pass

class ActionGroup:
    def __init__(self, name, action_dict):
        self.name = name
        self.actions = defaultdict(set)

def convert_rigify_rig(context, original_armature, name_suffix):
    if original_armature.data.get("rig_id") is None:
        raise TypeError(f"Object {original_armature} is not a Rigify rig.")

    if not context.mode == "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    
    #
    # Find root bone.
    #

    root_bone_candidates = [
        x for x in original_armature.data.bones if
        (x.parent is None or x.parent == "") and not x.name.startswith("DEF-") and not x.name.startswith("ORG-") and not x.name.startswith("MCH-")
    ]
    if len(root_bone_candidates) != 1:
        raise RuntimeError(f"Couldn't find root bone in armature \"{original_armature.name}\".")
    original_root_bone = root_bone_candidates[0]

    #
    # Create new rig object.
    #

    # Find object to overwrite.
    new_rig_name = f"{original_armature.name}{name_suffix}"
    new_armature_data_name = new_rig_name
    overwrite_rig_object = None
    try:
        found_object = bpy.data.objects[new_rig_name]
        if found_object.type == "ARMATURE":
            overwrite_rig_object = found_object
        else:
            bpy.data.objects.remove(found_object)
    except KeyError:
        pass

    created_armature_data = bpy.data.armatures.new("temp")
    if overwrite_rig_object is not None:
        old_armature_data = overwrite_rig_object.data
        overwrite_rig_object.data = created_armature_data
        created_rig = overwrite_rig_object
    else:
        created_rig = bpy.data.objects.new(new_rig_name, created_armature_data)
        context.scene.collection.objects.link(created_rig)

    if overwrite_rig_object is not None:
        bpy.data.armatures.remove(old_armature_data)
    created_rig.data.name = new_armature_data_name

    # Make rig object's collection included and visible.
    layer_collections = misc.find_layer_collections(created_rig)
    for layer_collection in layer_collections:
        layer_collection.exclude = False
        layer_collection.hide_viewport = False

    #
    # Create new mesh objects.
    #

    for child_mesh in (x for x in original_armature.children if x.type == "MESH"):
        new_mesh_name = f"{child_mesh.name}{name_suffix}"
        new_mesh_data_name = new_mesh_name
        overwrite_mesh_object = None
        try:
            found_object = bpy.data.objects[new_mesh_name]
            if found_object.type == "MESH":
                overwrite_mesh_object = found_object
            else:
                bpy.data.objects.remove(found_object)
        except KeyError:
            pass
        
        created_mesh_data = child_mesh.data.copy()
        if overwrite_mesh_object is not None:
            old_mesh_data = overwrite_mesh_object.data
            overwrite_mesh_object.data = created_mesh_data
            created_mesh = overwrite_mesh_object
        else:
            created_mesh = bpy.data.objects.new(new_mesh_name, created_mesh_data)
            context.scene.collection.objects.link(created_mesh)

        if overwrite_mesh_object is not None:
            bpy.data.meshes.remove(old_mesh_data)
        created_mesh.data.name = new_mesh_data_name

        # Parent mesh to rig and add armature modifier.
        created_mesh.parent = created_rig
        while len(created_mesh.modifiers) > 0:
            created_mesh.modifiers.remove(created_mesh.modifiers[0])
        armatue_modifier = created_mesh.modifiers.new(name="Armature", type="ARMATURE")
        armatue_modifier.object = created_rig

    #
    # Get bone rolls.
    #

    # Copy the original rig.
    # This new rig won't actually be used for anything except to be able to access the bone roll variable in edit mode.
    # Would be nice if that variable existed in the normal bone data and not just the edit bones.
    bone_roll_rig_data = original_armature.data.copy()
    bone_roll_rig = bpy.data.objects.new("bone_roll_rig", bone_roll_rig_data)
    context.scene.collection.objects.link(bone_roll_rig)

    # Make collection included and visible.
    layer_collections = misc.find_layer_collections(bone_roll_rig)
    for layer_collection in layer_collections:
        layer_collection.exclude = False
        layer_collection.hide_viewport = False

    # Make linked data local.
    context_override = context.copy()
    context_override["selected_objects"] = [bone_roll_rig]
    with context.temp_override(**context_override):
        bpy.ops.object.make_local(type="SELECT_OBDATA")

    #
    # Copy bones to the new rig.
    #

    # Select the new rig.
    bpy.ops.object.select_all(action="DESELECT")
    created_rig.select_set(True)
    bone_roll_rig.select_set(True)
    context.view_layer.objects.active = created_rig

    bpy.ops.object.mode_set(mode="EDIT")

    # Add bones.
    def create_bone(original_bone):
        new_bone = created_rig.data.edit_bones.new(original_bone.name)
        new_bone.inherit_scale = original_bone.inherit_scale
        new_bone.use_inherit_rotation = original_bone.use_inherit_rotation
        new_bone.use_local_location = original_bone.use_local_location
        new_bone.use_relative_parent = original_bone.use_relative_parent
        new_bone.use_connect = original_bone.use_connect
        new_bone.parent = created_rig.data.edit_bones[original_bone.parent.name] if original_bone.parent != None else None
        new_bone.head = original_bone.head_local.copy()
        new_bone.tail = original_bone.tail_local.copy()
        new_bone.use_deform = original_bone.use_deform
        new_bone.roll = bone_roll_rig.data.edit_bones[original_bone.name].roll
        for child in original_bone.children:
            create_bone(child)

    for parentless_bone in (x for x in original_armature.data.bones if x.parent is None):
        create_bone(parentless_bone)

    bpy.ops.object.mode_set(mode="POSE")

    # Remove bone roll rig.
    bpy.data.objects.remove(bone_roll_rig)
    bpy.data.armatures.remove(bone_roll_rig_data)

    #
    # Modify rigify bones.
    #

    bpy.ops.object.mode_set(mode="EDIT")

    # Find deform bones and replace their parents with a deform version of the parent bone.
    for edit_bone in (x for x in created_rig.data.edit_bones if x.name.startswith("DEF-") and x.parent is not None):
        def get_new_parent(edit_bone):
            if edit_bone.parent.name.startswith("DEF-"):
                return edit_bone.parent
            if edit_bone.parent.name.startswith("ORG-"):
                return created_rig.data.edit_bones[misc.replace_prefix(edit_bone.parent.name, "ORG", "DEF")]
            return None
        new_parent = get_new_parent(edit_bone)
        if new_parent is not None and new_parent.name == edit_bone.name:
            new_parent = get_new_parent(edit_bone.parent)
        edit_bone.parent = new_parent
    
    # Remove non-deform bones (but keep root).
    root_bone = created_rig.data.edit_bones[original_root_bone.name]
    for edit_bone in created_rig.data.edit_bones:
        if edit_bone != root_bone and not edit_bone.name.startswith("DEF-"):
            created_rig.data.edit_bones.remove(edit_bone)

    # Set the parent of parentless bones to the root bone.
    for edit_bone in created_rig.data.edit_bones:
        if edit_bone.parent is None:
            edit_bone.parent = root_bone

    #
    # Add copy constraints.
    #

    bpy.ops.object.mode_set(mode = "OBJECT")

    bpy.ops.object.select_all(action="DESELECT")
    created_rig.select_set(True)
    context.view_layer.objects.active = created_rig

    bpy.ops.object.mode_set(mode = "POSE")

    # Add constraints to copy transforms from the original rig.
    for pose_bone in created_rig.pose.bones:
        # Remove old constraints.
        while len(pose_bone.constraints) > 0:
            pose_bone.constraints.remove(pose_bone.constraints[0])
        # Add copy constraint.
        new_constraint = pose_bone.constraints.new("COPY_TRANSFORMS")
        new_constraint.target = original_armature
        new_constraint.subtarget = pose_bone.name
    
    bpy.ops.object.mode_set(mode = "OBJECT")
    
    return created_rig
