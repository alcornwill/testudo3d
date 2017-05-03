# Modular Building Tool (MBT)
(todo youtube video)  
create modular scenes, a common technique in game development
## features
* 'paint' with modules in 3D
* keyboard controls  
(mouse could be supported in the future) 
* organise modules into groups
* 'room' generator
* (more generators maybe in the future)
## modules
modules should be 1x1x1 or smaller  
multi-cell modules may be supported in the future
## module groups
modules are organised into groups  
when you paint over a module of the same group it is replaced  
however, one module of each group can coexist in the same 'cell'  
the exception to this is 'walls'. there can be one for each side of the cell  
groups also have special meaning when using generators
## room generator
'room' is a special module group that automatically generates the walls, floors and ceilings for a room of any shape  

there are 3 paint modes:
* __Active Module__: use the active module of each module group
* __Weighted Random__: uses weights defined in metadata
* __Dither__: dither between the first two modules in the group  
(could be useful for windows)
# usage
MBT uses the mesh data in your blend file to build with    
## setup
* assign a __module type__ to meshes you want to use as modules  
Properties > Data > MBT > Module Type  
this will assign a custom property to the mesh data  
(object transformation doesn't matter, only the mesh data is used)
* you can work with the modules like this, but you probably want to save this .blend file and use as a __module library__.
Work in a new .blend file and link your module library (file > link)
## workflow
* in 3D view press SPACE and search for 'modular building tool'
* now it should be running. it is a modal operator, so it will be active and override many keyboard shortcuts until you exit with ESC
* the selected object will become the 'root object'. modules are children of the root object
(if no object is selected an empty will be created)
* notice the __3d cursor arrow__, which has a direction
## controls
* __cursor keys__ move the 3d cursor arrow
* __ENTER__ paints a module
* __CTRL UP/DOWN__ move up and down
* __TAB__ cycle the module
* __SHIFT TAB__ cycle the module group
* __X__ delete
* __CTRL C/V__ copy/paste
* (__G__ to grab. still buggy)
# usage advanced
once you exit the tool, you can move the root object and rotate it. scaling is not recommended
## more controls
* __SHIFT cursor keys__ move faster
* __CTRL LEFT/RIGHT__ strafe
* __SHIFT X__ clear
## metadata json
some features of MBT require a metadata json file  
see the example metadata  
## constraints
you can go even further with modularity by joining together rooms with constraints    
__Connect Portals__ is another feature of MBT to make this easier  
* select two objects
* SPACE > Connect Portals

this will create a CopyLocation and CopyRotation constraint on the first object
