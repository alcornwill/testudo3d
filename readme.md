# Modular Building Tool (MBT)
(todo youtube video)  
create modular scenes, a common technique in game development
## features
* __'paint' with modules in 3D__
* __keyboard controls__  
(mouse could be supported in the future) 
* __organise modules into groups__
* __'room' generator__  
(more generators maybe in the future)
## modules
modules should be 1x1x1 or smaller  
multi-cell modules may be supported in the future
## module groups
Modules are organised into groups  
When you paint over a module of the same group it is replaced  
However, one module of each group can coexist in the same 'cell'  
The exception to this is 'walls'. there can be one for each side of the cell  
Though you can name a group whatever you like, __groups also have special meaning when using generators__
## room generator
'room' is a special module group that automatically generates the walls, floors and ceilings for a room of any shape  

there are 3 paint modes:
* __Active Module__: use the active module of each module group
* __Weighted Random__: uses weights defined in metadata
* __Dither__: dither between the first two modules in the group  
(could be useful for windows) 

you can also add custom rooms with the metadata json (see example)
# usage
MBT uses the mesh data in your blend file to build with    
## setup
* assign a __module type__ to meshes you want to use as modules  
3D View > MBT > Set Module Type  
this will assign a custom property to the mesh data of selected objects  
(object transformation doesn't matter, only the mesh data is used)
* you can work with the modules like this, but you probably want to save this .blend file and use as a __module library__.
Work in a new .blend file and link your module library (3D View > MBT > Link Module Library)
## workflow
* activate __modular building mode__ (3D VIEW > MBT > Modular Building Mode)
* the selected object will become the __root object__. modules are children of the root object
(if no object is selected an empty will be created)
* notice the __3d cursor arrow__, which has a direction
* modular building mode will override many keyboard shortcuts until you exit with __ESC__
## controls
* __cursor keys__ move the 3d cursor arrow
* __ENTER__ paints a module
* __CTRL UP/DOWN__ move up and down
* __TAB / SHIFT TAB__ cycle the module
* __1-9__ set active module group
* __X__ delete
* __CTRL C/V__ copy/paste
* (__G__ to grab. still buggy)
# usage advanced
once you exit the tool, you can move the root object and rotate it. scaling is not recommended
## more controls
* __SHIFT cursor keys__ move faster
* __CTRL LEFT/RIGHT__ strafe
* __SHIFT X__ clear
* __B__ 3D box select (__ENTER__, __X__, __SHIFT X__ work like normal)
## metadata json
some features of MBT require a metadata json file  
see the example metadata  
## constraints
you can go even further with modularity by joining together rooms with constraints    
__Connect Portals__ is another feature of MBT to make this easier  
* select two objects
* SPACE > Connect Portals

this will create a CopyLocation and CopyRotation constraint on the first object
