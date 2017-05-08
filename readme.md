# Modular Building Tool (MBT)
(todo youtube video)  
create modular scenes, a common technique in game development
### Features
* __'paint' with modules in 3D__
* __keyboard controls__  
(mouse could be supported in the future) 
* __organise modules into groups__
* __'room' generator__  
(more generators maybe in the future)
### Known Issues
* room generator doesn't really work, leaves garbage in middle of room.  
is also unnecessarily slow
* Sometimes copy/paste deletes walls
* copy/paste/grab doesn't work with box select (haven't got round to it)  
* undo / redo doesn't work  
(changes are still pushed to undo stack when you exit tool)

## Install
in blender:
* File > User Preferences
* Add-ons > Install from File
* navigate to __modular_building_tool__ directory
* after installed, search for and enable 'modular building tool'
## Usage
MBT uses the mesh data in your blend file to build with    
### Setup
* assign a __module type__ to meshes you want to use as modules  
3D View > MBT > Set Module Type  
this will assign a custom property to the mesh data of selected objects  
(object transformation doesn't matter, only the mesh data is used)
* you can work with the modules like this, but you probably want to save this .blend file and use as a __module library__.
Work in a new .blend file and link your module library (3D View > MBT > Link Module Library)
### Workflow
* activate __modular building mode__ (3D VIEW > MBT > Modular Building Mode)
* the selected object will become the __root object__. modules are children of the root object
(if no object is selected an empty will be created)
* notice the __3d cursor arrow__, which has a direction
* modular building mode will override many keyboard shortcuts until you exit with __ESC__
### Controls
* __cursor keys__ move the 3d cursor arrow
* __ENTER__ paints a module
* __CTRL UP/DOWN__ move up and down
* __TAB / SHIFT TAB__ cycle the module
* __1-9__ set active module group
* __X__ delete
* __CTRL C/V__ copy/paste
* __G__ to grab (__ESC__ to cancel)

see [wiki](https://github.com/alcornwill/modular_building_tool/wiki) for more info