from collections import defaultdict
import bpy
import math
from . import misc

class RigConverterException(Exception):
    pass

class ActionGroup:
    def __init__(self, name, action_dict):
        self.name = name
        self.actions = defaultdict(set)

def convert_rigify_rig(context, original_rig, original_mesh, original_actions, root_bone_name, modified_frame_ranges):
    is_rigify_rig = misc.is_rigify_rig(original_rig)
    new_rig_name = f"{original_rig.name}_Converted"
    new_armature_data_name = new_rig_name
    new_mesh_name = f"{original_mesh.name}_Converted"
    new_mesh_data_name = new_mesh_name

    try:
        overwrite_rig_object = bpy.data.objects[new_rig_name]
    except:
        overwrite_rig_object = None
    try:
        overwrite_mesh_object = bpy.data.objects[new_mesh_name]
    except:
        overwrite_mesh_object = None

    if not context.mode == "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    #
    # Get bone rolls.
    #

    # Copy the original rig.
    # This new rig won't actually be used for anything except to be able to access the bone roll variable in edit mode.
    # Would be nice if that variable existed in the normal bone data and not just the edit bones.
    bone_roll_rig_data = original_rig.data.copy()
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
    # Create new rig object.
    #

    created_armature_data = bpy.data.armatures.new("temp")
    if overwrite_rig_object != None:
        old_armature_data = overwrite_rig_object.data
        overwrite_rig_object.data = created_armature_data
        created_rig = overwrite_rig_object
    else:
        created_rig = bpy.data.objects.new(new_rig_name, created_armature_data)
        context.scene.collection.objects.link(created_rig)

    if overwrite_rig_object != None:
        bpy.data.armatures.remove(old_armature_data)
    created_rig.data.name = new_armature_data_name

    # Make rig object's collection included and visible.
    layer_collections = misc.find_layer_collections(created_rig)
    for layer_collection in layer_collections:
        layer_collection.exclude = False
        layer_collection.hide_viewport = False

    #
    # Create new mesh object.
    #
    
    created_mesh_data = original_mesh.data.copy()
    if overwrite_mesh_object != None:
        old_mesh_data = overwrite_mesh_object.data
        overwrite_mesh_object.data = created_mesh_data
        created_mesh = overwrite_mesh_object
    else:
        created_mesh = bpy.data.objects.new(new_mesh_name, created_mesh_data)
        context.scene.collection.objects.link(created_mesh)

    if overwrite_mesh_object != None:
        bpy.data.meshes.remove(old_mesh_data)
    created_mesh.data.name = new_mesh_data_name

    # Parent mesh to rig and add armature modifier.
    created_mesh.parent = created_rig
    while len(created_mesh.modifiers) > 0:
        created_mesh.modifiers.remove(created_mesh.modifiers[0])
    armatue_modifier = created_mesh.modifiers.new(name="Armature", type="ARMATURE")
    armatue_modifier.object = created_rig

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

    for parentless_bone in (x for x in original_rig.data.bones if x.parent == None):
        create_bone(parentless_bone)

    bpy.ops.object.mode_set(mode="POSE")

    # Remove bone roll rig.
    bpy.data.objects.remove(bone_roll_rig)
    bpy.data.armatures.remove(bone_roll_rig_data)

    #
    # Modify rigify bones.
    #

    bpy.ops.object.mode_set(mode="EDIT")

    if is_rigify_rig:
        root_bone = created_rig.data.edit_bones[root_bone_name]

        # Find deform bones and replace their parents with a deform version of the parent bone.
        for edit_bone in (x for x in created_rig.data.edit_bones if x.name.startswith("DEF-") and x.parent != None):
            def getNewParent(edit_bone):
                if edit_bone.parent.name.startswith("DEF-"):
                    return edit_bone.parent
                if edit_bone.parent.name.startswith("ORG-"):
                    return created_rig.data.edit_bones[misc.replace_prefix(edit_bone.parent.name, "ORG", "DEF")]
                return None
            new_parent = getNewParent(edit_bone)
            if new_parent != None and new_parent.name == edit_bone.name:
                new_parent = getNewParent(edit_bone.parent)
            edit_bone.parent = new_parent
        
        # Remove non-deform bones (but keep root).
        for edit_bone in created_rig.data.edit_bones:
            if edit_bone != root_bone and not edit_bone.name.startswith("DEF-"):
                created_rig.data.edit_bones.remove(edit_bone)

        # Set the parent of parentless bones to the root bone.
        for edit_bone in created_rig.data.edit_bones:
            if edit_bone.parent == None:
                edit_bone.parent = root_bone

    #
    # Bake actions.
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
        new_constraint.target = original_rig
        new_constraint.subtarget = pose_bone.name
    
    # Store animation data action.
    old_original_rig_action = original_rig.animation_data.action if original_rig.animation_data != None else None

    created_actions = []
    for action in original_actions:
        if original_rig.animation_data == None:
            original_rig.animation_data_create()
        original_rig.animation_data.action = action
        created_rig.animation_data_clear()
        frame_range = modified_frame_ranges[action]

        # Clear transforms for all bones.
        bpy.ops.pose.select_all(action = "SELECT")
        bpy.ops.pose.loc_clear()
        bpy.ops.pose.rot_clear()
        bpy.ops.pose.scale_clear()

        # Bake.
        print(f"action.name: {action.name}, frame_start: {frame_range[0]}, frame_end: {frame_range[1]}")
        bpy.ops.nla.bake(
            frame_start = frame_range[0],
            frame_end = frame_range[1],
            only_selected = True,
            visual_keying = True,
            clear_constraints = False,
            clear_parents = False,
            use_current_action = False,
            bake_types = {"POSE"}
        )

        # Clear transforms for all bones.
        bpy.ops.pose.select_all(action = "SELECT")
        bpy.ops.pose.loc_clear()
        bpy.ops.pose.rot_clear()
        bpy.ops.pose.scale_clear()

        # Rename the created action.
        old_name = action.name
        new_name = f"{old_name}_Converted"

        # If an action with the same name exists, remove it.
        action_index = bpy.data.actions.find(new_name)
        if action_index > -1:
            bpy.data.actions.remove(bpy.data.actions[action_index])

        created_action = created_rig.animation_data.action
        created_action.name = new_name
        created_action.use_fake_user = True

        # Remove curves that don't have a bone.
        pending_removal = [
            fcurve for fcurve in created_action.fcurves
            if not any(
                (bone.name in fcurve.data_path) for bone in created_rig.data.bones
            )
        ]
        for x in pending_removal:
            action.fcurves.remove(x)

        created_actions.append(created_action)
    
    # Restore old animation data action.
    if original_rig.animation_data != None:
        original_rig.animation_data.action = old_original_rig_action

    # Remove constraints
    for pose_bone in created_rig.pose.bones:
        while len(pose_bone.constraints) > 0:
            pose_bone.constraints.remove(pose_bone.constraints[0])
    
    bpy.ops.object.mode_set(mode = "OBJECT")

    #
    # Rename bones.
    #

    bpy.ops.object.mode_set(mode = "EDIT")

    if is_rigify_rig:
        # Remove DEF prefix from bone names.
        for edit_bone in created_rig.data.edit_bones:
            if edit_bone.name.startswith("DEF-"):
                edit_bone.name = misc.replace_prefix(edit_bone.name, "DEF-", "")

        # Remove DEF prefix from action channel names.
        for action in created_actions:
            for fcurve in action.fcurves:
                fcurve.data_path = fcurve.data_path.replace("DEF-", "")
            for group in action.groups:
                group.name = group.name.replace("DEF-", "")

    # Rename root.
    created_rig.data.edit_bones[root_bone_name].name = "root"

    # Rename root in action channel names.
    for action in created_actions:
        for fcurve in (x for x in action.fcurves if root_bone_name in x.data_path):
            fcurve.data_path = fcurve.data_path.replace(root_bone_name, "root")
        for group in (x for x in action.groups if root_bone_name in x.name):
            group.name = group.name.replace(root_bone_name, "root")

    bpy.ops.object.mode_set(mode = "OBJECT")
