# Modular Building Tool (MBT)
(todo youtube video)  
create modular scenes, a common technique in game development
##### features
* 'paint' with modules in 3D
* keyboard controls  
(mouse could be supported in the future) 
* organise modules into groups
* 'room' generator
* (more generators maybe in the future)
##### modules
modules should be 1x1x1 or smaller  
multi-cell modules may be supported in the future
##### module groups
modules are organised into groups  
when you paint over a module of the same group it is replaced  
however, one module of each group can coexist in the same 'cell'  
the exception to this is 'walls'. there can be one for each side of the cell (4)  
groups also have special meaning when using generators
##### room generator
'room' is a special module group that automatically generates the walls, floors and ceilings for a room of any shape  

there are 3 paint modes:
* __Active Module__: use the active module of each module group
* __Weighted Random__: uses weights defined in metadata
* __Dither__: dither between the first two modules in the group  
(could be useful for windows)
# usage
MBT uses the mesh data in your blend file to build with    
##### workflow
* link your .blend file with your modules in (file->link)  
  (object transformation doesn't matter, only the mesh data is used)
* in 3D view press SPACE and search for 'modular building tool'
* now it should be running. it is a modal operator, so it will be active and override many keyboard shortcuts until you exit with ESC
* the selected object will become the 'root object'. modules are children of the root object
(if no object is selected an empty will be created)
* notice the __3d cursor arrow__, which has a direction
#### metadata json
you must register the modules you want to paint with in "modular_building_tool\metadata.json"  
see the example metadata  

##### metadata format
* __type__: the module group name. 
can be anything, but some have special meaning 
(only 'floor', 'wall' and 'ceiling' currently) 
* __weight__: 'room' paint has a 'weighted random' mode, which uses this value  
 
#### controls
* cursor keys move the 3d cursor arrow
* ENTER paints a module at the cursor position
* SHIFT UP/DOWN move up and down
* TAB cycle the module
* SHIFT TAB cycle the module group
* (G to grab. still buggy)
# usage advanced
once you exit the tool, you can move the root object and rotate it. scaling is not recommended  
#### constraints
you can go even further with modularity by joining together rooms with constraints    
__Connect Portals__ is another feature of MBT to make this easier  
* select two objects
* SPACE > Connect Portals

this will create a CopyLocation and CopyRotation constraint on the first object
