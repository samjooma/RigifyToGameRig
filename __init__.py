bl_info = {
    "name": "Rigify to game rig converter",
    "description": "Converts a rigify rig and its animations into a basic rig compatible with game engines",
    "author": "Samjooma",
    "version": (1, 0, 0),
    "blender": (4, 1, 0),
    "category": "Rigging"
}

import bpy
from . import converter_operator

def register():
    converter_operator.register()

def unregister():
    converter_operator.unregister()

if __name__ == "__main__":
    register()