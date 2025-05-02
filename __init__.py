bl_info = {
    "name": "Simple Rigify Duplication",
    "description": "Create a simplified duplicate of a Rigify armature and make the new armature follow the transformations of the original",
    "author": "Samjooma",
    "version": (1, 0, 0),
    "blender": (4, 4, 1),
    "category": "Rigging"
}

import bpy
from . import duplicator_operator

def register():
    duplicator_operator.register()

def unregister():
    duplicator_operator.unregister()

if __name__ == "__main__":
    register()