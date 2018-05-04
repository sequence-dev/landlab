#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Create a Lithology object with different properties."""

import numpy as np
from landlab.layers import EventLayers, MaterialLayers


class Lithology(object):
    """Create a Lithology object.

    A Lithology is a three dimentional representation of material operated on
    by landlab components. Material can be removed through erosion or added to
    through deposition. Rock types can have multiple attributes (e.g. age,
    erodability or other parameter values, etc).

    If the tracked properties are model grid fields, they will be updated to
    the surface values of the Lithology. If the properties are not grid fields
    then at-node grid fields will be created with their names. Lithology and
    its derived versions will make a at-node grid field called `rock_type__id`
    to store the rock type id.

    Lithology was designed to be used on its own and to be inherited from and
    improved. Currently one other Lithology variant exists: LithoLayers
    which makes it easy to specify parallel layers of rock with generic layer
    geometries.

    It is constructed by specifying a series of thicknesses and a series of
    rock type IDs. Thicknesses and IDs are both specified in order of closest
    to the surface to furthest from the surface. Thicknesses can either be a
    single value (cooresponding to a layer of uniform thickness) or a number-of
    -nodes length array (cooresponding to a non-uniform layer).

    Additionally, an attribute dictionary specifies the properties of each
    rock type. This dictionary is expected to have the form of:

    .. code-block:: python

        attrs = {'K_sp': {1: 0.001,
                          2: 0.0001},
                 'D': {1: 0.01,
                       2: 0.001}}

    Where ``'K_sp'`` and ``'D'`` are properties to track, and ``1`` and ``2``
    are rock type IDs. The rock type IDs can be any type that is valid as a
    python dictionary key.

    Attributes
    ----------
    z_top
    z_bottom
    thickness
    dz
    tracked_properties
    properties

    Methods
    -------
    add_rock_type
    add_rock_attribute
    update_rock_properties
    add_layer
    run_one_step
    """

    _name = 'Lithology'

    _cite_as = """ """

    def __init__(self, grid, thicknesses, ids, attrs, layer_type = "EventLayers"):
        """Create a new instance of Lithology.

        Parameters
        ----------
        grid : Landlab ModelGrid
        thicknesses : ndarray of shape `(n_layers, )` or `(n_layers, n_nodes)`
            Values of layer thicknesses from surface to depth. Layers do not
            have to have constant thickness. Layer thickness can be zero,
            though the entirety of Lithology must have non-zero thickness.
        ids : ndarray of shape `(n_layers, )` or `(n_layers, n_nodes)`
            Values of rock type IDs cooresponding to each layer specified in
            **thicknesses**. A single layer may have multiple rock types if
            specified by the user.
        attrs : dict
            Rock type property dictionary. See class docstring for example of
            required format.
        layer_type : str, optional
            Type of Landlab layers object used to store the layers. If
            MaterialLayers (default) is specified, then erosion removes material
            and does not create a layer of thickness zero. If EventLayers is
            used, then erosion removes material and creates layers of thickness
            zero. Thus, EventLayers may be appropriate if the user is interested
            in chronostratigraphy.

        Examples
        --------
        >>> from landlab import RasterModelGrid
        >>> from landlab.components import Lithology
        >>> mg = RasterModelGrid(3, 3)
        >>> z = mg.add_zeros('node', 'topographic__elevation')

        Create a Lithology with uniform thicknesses that alternates between
        layers of type 1 and type 2 rock.

        >>> thicknesses = [1, 2, 4, 1]
        >>> ids = [1, 2, 1, 2]
        >>> attrs = {'K_sp': {1: 0.001,
        ...                   2: 0.0001}}
        >>> lith = Lithology(mg, thicknesses, ids, attrs)

        After creating a Lithology, the model grid will have an at-node grid
        field set to the surface values of 'K_sp'.

        >>> mg.at_node['K_sp']
        array([ 0.001,  0.001,  0.001,  0.001,  0.001,  0.001,  0.001,  0.001,
            0.001])

        The surface values are also properties of the Lithology.

        >>> lith['K_sp']
        array([ 0.001,  0.001,  0.001,  0.001,  0.001,  0.001,  0.001,  0.001,
            0.001])

        We can access information about the Lithology like the total thickness
        or layer thicknesses.

        >>> lith.thickness
        array([ 8.,  8.,  8.,  8.,  8.,  8.,  8.,  8.,  8.])
        >>> lith.dz
        array([[ 1.,  1.,  1.,  1.,  1.,  1.,  1.,  1.,  1.],
               [ 4.,  4.,  4.,  4.,  4.,  4.,  4.,  4.,  4.],
               [ 2.,  2.,  2.,  2.,  2.,  2.,  2.,  2.,  2.],
               [ 1.,  1.,  1.,  1.,  1.,  1.,  1.,  1.,  1.]])

        This might look confusing -- that the layers are in reverse order, but
        it is OK. The last layers in the Lithology are those that are closest
        to the surface.

        The layers don't all have to have the same thickness as in the prior
        example. If the layers have non-uniform thickness, then they must be
        specified in an array of shape `(n_layer, n_nodes)`. In this case, the
        layer IDs must be specified in either an array of `(n_layer)` or
        `(n_layer, n_nodes)`.

        Here we make a layer that gets thicker as a function of the x value of
        the model grid.

        >>> layer_pattern = (0.5 * mg.x_of_node) + 1.0
        >>> thicknesses = [1*layer_pattern, 2*layer_pattern, 4*layer_pattern]
        >>> ids = [1, 2, 1]
        >>> lith = Lithology(mg, thicknesses, ids, attrs)
        >>> lith.thickness
        array([  7. ,  10.5,  14. ,   7. ,  10.5,  14. ,   7. ,  10.5,  14. ])
        >>> lith.dz
        array([[ 4. ,  6. ,  8. ,  4. ,  6. ,  8. ,  4. ,  6. ,  8. ],
               [ 2. ,  3. ,  4. ,  2. ,  3. ,  4. ,  2. ,  3. ,  4. ],
               [ 1. ,  1.5,  2. ,  1. ,  1.5,  2. ,  1. ,  1.5,  2. ]])
        """
        # save reference to the grid and the last time steps's elevation.
        self._grid = grid

        try:
            self.last_elevation = self._grid['node']['topographic__elevation'][:].copy()
        except KeyError:
            msg = ('Lithology requires that topographic__elevation already '
                   'exists as an at-node field.')
            raise ValueError(msg)

        # save inital information about thicknesses, layers, attributes, and ids.
        self._init_thicknesses = np.asarray(thicknesses)
        self._attrs = attrs
        self._number_of_init_layers = self._init_thicknesses.shape[0]
        self._properties = list(attrs.keys())

        # assert that thicknesses and ids are correct and consistent shapes

        # if thickness is a 2d array.
        if self._init_thicknesses.ndim == 2:

            # assert that the 2nd dimension is the same as the number of nodes.
            if self._init_thicknesses.shape[1] != self._grid.number_of_nodes:
                msg = ('Thicknesses provided to Lithology are ',
                       'inconsistent with the ModelGrid.')
                raise ValueError(msg)

            # if IDs is a 2d array assert that it is the same size as thicknesses
            if np.asarray(ids).ndim == 2:
                if self._init_thicknesses.shape != np.asarray(ids).shape:
                    msg = ('Thicknesses and IDs provided to Lithology are ',
                           'inconsistent with each other.')
                    raise ValueError(msg)
                # if tests pass set value of IDs.
                self._ids = np.asarray(ids)

            # if IDS is a 1d array
            elif np.asarray(ids).ndim == 1:
                if np.asarray(ids).size != self._number_of_init_layers:
                    msg = ('Number of IDs provided to Lithology is ',
                           'inconsistent with number of layers provided in '
                           'thicknesses.')
                    raise ValueError(msg)
                # if tests pass, broadcast ids to correct shape.
                self._ids = np.broadcast_to(np.atleast_2d(np.asarray(ids)).T,
                                            self._init_thicknesses.shape)

            else:
                msg = ('IDs must be of shape `(n_layers, )` or `(n_layers, '
                       'n_nodes)`. Passed array has more than 2 dimensions.')
                raise ValueError(msg)

        elif self._init_thicknesses.ndim == 1:
            if self._init_thicknesses.shape != np.asarray(ids).shape:
                msg = ('Thicknesses and IDs provided to Lithology are ',
                           'inconsistent with each other.')
                raise ValueError(msg)
            self._ids = np.asarray(ids)
        else:
            msg = ('Thicknesses must be of shape `(n_layers, )` or `(n_layers, '
                   'n_nodes)`. Passed array has more than 2 dimensions.')
            raise ValueError(msg)

        # assert that attrs are pointing to fields (or create them)
        for at in self._properties:
            if at not in grid.at_node:
                self._grid.add_empty('node', at)

        # add a field for the rock type id
        if 'rock_type__id' not in self._grid.at_node:
            self._grid.add_empty('node', 'rock_type__id')

        # verify that all IDs have attributes.
        self._check_property_dictionary()

        # create a EventLayers instance
        if layer_type == 'EventLayers':
            self._layers = EventLayers(grid.number_of_nodes,
                                       self._number_of_init_layers)
        elif layer_type == 'MaterialLayers':
            self._layers = MaterialLayers(grid.number_of_nodes,
                                          self._number_of_init_layers)
        else:
            raise ValueError(('Lithology passed an invalid option for '
                              'layer type.'))

        # From bottom to top, add layers to the Lithology with attributes.
        for i in range(self._number_of_init_layers-1, -1, -1):
            try:
                self.add_layer(self._init_thicknesses[i, :], self._ids[i, :])
            except IndexError:
                self.add_layer(self._init_thicknesses[i], self._ids[i])

        # check that rock exists at the surface everywhere.
        if np.any(self._layers.thickness <= 0):
            msg = ('Lithology was instantiated with a thickness of '
                   'zero at at least one node.')
            raise ValueError(msg)

    def __getitem__(self, name):
        return self._layers.surface_values(name)

    @property
    def tracked_properties(self):
        """Properties tracked by Lithology.

        Examples
        --------
        >>> from landlab import RasterModelGrid
        >>> from landlab.components import Lithology
        >>> mg = RasterModelGrid(3, 3)
        >>> z = mg.add_zeros('node', 'topographic__elevation')
        >>> thicknesses = [1, 2, 4, 1]
        >>> ids = [1, 2, 1, 2]
        >>> attrs = {'K_sp': {1: 0.001,
        ...                   2: 0.0001}}
        >>> lith = Lithology(mg, thicknesses, ids, attrs)
        >>> lith.tracked_properties
        ['K_sp']
        """
        self._properties.sort()
        return self._properties

    @property
    def properties(self):
        """Properties dictionary used by Lithology.

        Examples
        --------
        >>> from landlab import RasterModelGrid
        >>> from landlab.components import Lithology
        >>> mg = RasterModelGrid(3, 3)
        >>> z = mg.add_zeros('node', 'topographic__elevation')
        >>> thicknesses = [1, 2, 4, 1]
        >>> ids = [1, 2, 1, 2]
        >>> attrs = {'K_sp': {1: 0.001,
        ...                   2: 0.0001}}
        >>> lith = Lithology(mg, thicknesses, ids, attrs)
        >>> lith.properties
        {'K_sp': {1: 0.001, 2: 0.0001}}
        """
        return self._attrs

    @property
    def thickness(self):
        """Total thickness of the Lithology at each node.

        Examples
        --------
        >>> from landlab import RasterModelGrid
        >>> from landlab.components import Lithology
        >>> mg = RasterModelGrid(3, 3)
        >>> z = mg.add_zeros('node', 'topographic__elevation')
        >>> thicknesses = [1, 2, 4, 1]
        >>> ids = [1, 2, 1, 2]
        >>> attrs = {'K_sp': {1: 0.001,
        ...                   2: 0.0001}}
        >>> lith = Lithology(mg, thicknesses, ids, attrs)
        >>> lith.thickness
        array([ 8.,  8.,  8.,  8.,  8.,  8.,  8.,  8.,  8.])
        """
        return self._layers.thickness

    @property
    def dz(self):
        """Thickness of each layer in the Lithology at each node.

        The thickness of each layer in the Lithology as an array of shape
        `(number_of_layers, number_of_nodes)`.

        Examples
        --------
        >>> from landlab import RasterModelGrid
        >>> from landlab.components import Lithology
        >>> mg = RasterModelGrid(3, 3)
        >>> z = mg.add_zeros('node', 'topographic__elevation')
        >>> thicknesses = [1, 2, 4, 1]
        >>> ids = [1, 2, 1, 2]
        >>> attrs = {'K_sp': {1: 0.001,
        ...                   2: 0.0001}}
        >>> lith = Lithology(mg, thicknesses, ids, attrs)
        >>> lith.dz
        array([[ 1.,  1.,  1.,  1.,  1.,  1.,  1.,  1.,  1.],
               [ 4.,  4.,  4.,  4.,  4.,  4.,  4.,  4.,  4.],
               [ 2.,  2.,  2.,  2.,  2.,  2.,  2.,  2.,  2.],
               [ 1.,  1.,  1.,  1.,  1.,  1.,  1.,  1.,  1.]])
        """
        return self._layers.dz

    @property
    def z_bottom(self):
        """Thickness from the surface to the bottom of each layer in Lithology.

        Thickness from the topographic surface to the bottom of each layer as
        an array of shape `(number_of_layers, number_of_nodes)`.

        Examples
        --------
        >>> from landlab import RasterModelGrid
        >>> from landlab.components import Lithology
        >>> mg = RasterModelGrid(3, 3)
        >>> z = mg.add_zeros('node', 'topographic__elevation')
        >>> thicknesses = [1, 2, 4, 1]
        >>> ids = [1, 2, 1, 2]
        >>> attrs = {'K_sp': {1: 0.001,
        ...                   2: 0.0001}}
        >>> lith = Lithology(mg, thicknesses, ids, attrs)
        >>> lith.z_bottom
        array([[ 8.,  8.,  8.,  8.,  8.,  8.,  8.,  8.,  8.],
               [ 7.,  7.,  7.,  7.,  7.,  7.,  7.,  7.,  7.],
               [ 3.,  3.,  3.,  3.,  3.,  3.,  3.,  3.,  3.],
               [ 1.,  1.,  1.,  1.,  1.,  1.,  1.,  1.,  1.]])
        """
        thick = np.broadcast_to(self._layers.thickness, self._layers.z.shape)
        return thick - self._layers.z + self._layers.dz

    @property
    def z_top(self):
        """Thickness from the surface to the top of each layer in Lithology.

        Thickness from the topographic surface to the top of each layer as
        an array of shape `(number_of_layers, number_of_nodes)`.

        Examples
        --------
        >>> from landlab import RasterModelGrid
        >>> from landlab.components import Lithology
        >>> mg = RasterModelGrid(3, 3)
        >>> z = mg.add_zeros('node', 'topographic__elevation')
        >>> thicknesses = [1, 2, 4, 1]
        >>> ids = [1, 2, 1, 2]
        >>> attrs = {'K_sp': {1: 0.001,
        ...                   2: 0.0001}}
        >>> lith = Lithology(mg, thicknesses, ids, attrs)
        >>> lith.z_top
        array([[ 7.,  7.,  7.,  7.,  7.,  7.,  7.,  7.,  7.],
               [ 3.,  3.,  3.,  3.,  3.,  3.,  3.,  3.,  3.],
               [ 1.,  1.,  1.,  1.,  1.,  1.,  1.,  1.,  1.],
               [ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.]])
        """
        thick = np.broadcast_to(self._layers.thickness, self._layers.z.shape)
        return thick - self._layers.z

    def _check_property_dictionary(self):
        """Check compatibility of Lithology and property dictionary."""
        ids = []
        for at in self._properties:
            ids.extend(self._attrs[at].keys())
        self.ids = frozenset(np.unique(ids))

        for at in self._properties:
            for i in self.ids:
                if i not in self._attrs[at]:
                    msg = ('A rock type with ID value ' + str(i) + 'was '
                           'specified in Lithology. No value '
                           'for this ID was provided in property ' + at + '.')
                    raise ValueError(msg)

    def _update_surface_values(self):
        """Update Lithology surface values"""
        # Update surface values for each attribute.
        self._grid['node']['rock_type__id'][:] = self['rock_type__id']
        for at in self._properties:
            self._grid['node'][at][:] = self[at]

    def add_layer(self, thickness, rock_id=None):
        """Add a new layer to Lithology.

        Parameters
        ----------
        thickness : float or `(n_nodes,)` array
            Positive values deposit material on to Lithology while negative
            values erode Lithology.
        rock_id : single value or `n_nodes` long itterable, optional if only erosion occurs
            Rock type ID for new deposits. Can be single value or an number-
            of-nodes array.

        Examples
        --------
        >>> from landlab import RasterModelGrid
        >>> from landlab.components import Lithology
        >>> mg = RasterModelGrid(3, 3)
        >>> z = mg.add_zeros('node', 'topographic__elevation')
        >>> thicknesses = [1, 2, 4, 1]
        >>> ids = [1, 2, 1, 2]

        We can instantiate Lithology with rock type properties we know we will
        use in the future.

        >>> attrs = {'K_sp': {1: 0.001,
        ...                   2: 0.0001,
        ...                   3: 0.01}}
        >>> lith = Lithology(mg, thicknesses, ids, attrs)

        Add a layer of thickness 3 and rock type 3.

        >>> lith.add_layer(3, rock_id=3)

        The value of K_sp at node is now updated to the value of rock type 3

        >>> mg.at_node['K_sp']
        array([ 0.01,  0.01,  0.01,  0.01,  0.01,  0.01,  0.01,  0.01,  0.01])

        A negative value will erode. We can also pass a `(n_nodes,) long array
        to erode unevenly. If all parts of the layer erode, then no rock_id
        needs to be passed.

        >>> erosion_amount = [-2., -2., -2., -4., -4., -4., -6., -6., -6.]
        >>> lith.add_layer(erosion_amount)
        >>> mg.at_node['K_sp']
        array([ 0.01  ,  0.01  ,  0.01  ,  0.0001,  0.0001,  0.0001,  0.001 ,
        0.001 ,  0.001 ])

        Now different layers are exposed at the surface and the value of K_sp
        is spatially variable.
        """
        thickness = np.array(thickness)

        # verify that Lithology will still have thickness after change
        if np.any((self._layers.thickness + thickness) <= 0):
            msg = ('add_layer will result in Lithology having a thickness of '
                   'zero at at least one node.')
            raise ValueError(msg)

        # verify that rock type added exists.
        try:
            all_ids_present = self.ids.issuperset(rock_id)
            new_ids = rock_id
        except TypeError:
            all_ids_present = self.ids.issuperset([rock_id])
            new_ids = [rock_id]

        if all_ids_present == False:

            missing_ids = set(new_ids).difference(self.ids)

            if np.any(thickness>0):
                 msg = ('Lithology add_layer was given a rock type id that does '
                        'not yet exist and will need to deposit. Use a valid '
                        'rock type or add_rock_type. ' + str(missing_ids))
                 raise ValueError(msg)

        # collect attilithutes
        if rock_id is not None:
            new_layer_properties = {'rock_type__id': rock_id}
            for at in self._properties:
                try:
                    layer_value = list(map(self._attrs[at].get, rock_id))
                except TypeError: # if not iterable
                    layer_value = self._attrs[at].get(rock_id)

                new_layer_properties[at] = layer_value

            # add layer
            self._layers.add(thickness, **new_layer_properties)
        else:
            self._layers.add(thickness)

        # update surface values
        self._update_surface_values()

    def add_property(self, attrs):
        """Add new property to Lithology

        Parameters
        ----------
        attrs : dict
            Rock attribute dictionary for the new property(s).

        Examples
        --------
        >>> from landlab import RasterModelGrid
        >>> from landlab.components import Lithology
        >>> mg = RasterModelGrid(3, 3)
        >>> z = mg.add_zeros('node', 'topographic__elevation')
        >>> thicknesses = [1, 2, 4, 1]
        >>> ids = [1, 2, 1, 2]
        >>> attrs = {'K_sp': {1: 0.001,
        ...                   2: 0.0001}}
        >>> lith = Lithology(mg, thicknesses, ids, attrs)
        >>> lith.add_property({'D': {1: 0.03,
        ...                        2: 0.004}})
        >>> lith.tracked_properties
        ['D', 'K_sp']
        >>> mg.at_node['D']
        array([ 0.03,  0.03,  0.03,  0.03,  0.03,  0.03,  0.03,  0.03,  0.03])
        """
        for at in attrs:
            if at in self._properties:
                msg = ('add_property is trying to add an existing '
                       'attribute, this is not permitted. ' + str(at))
                raise ValueError(msg)

            new_rids = attrs[at].keys()
            for rid in new_rids:
                if rid not in self.ids:
                    msg = ('add_property has an attribute(' + str(at) + ')'
                           ' for rock type ' + str(rid) + ' that no other. Rock '
                           ' type has. This is not permitted.')
                    raise ValueError(msg)

            for rid in self.ids:
                if rid not in new_rids:
                    msg = ('add_property needs a value for id ' + str(rid) + ''
                           ' and attribute ' + str(at) + '.')
                    raise ValueError(msg)

        for at in attrs:
            if at not in self._grid.at_node:
                self._grid.add_empty('node', at)
            self._attrs[at] = attrs[at]
            self._properties.append(at)

            # update layers to add a tracked value.
            self._layers[at] = self._get_new_values(at)

        # update surface values
        self._update_surface_values()

    def add_rock_type(self, attrs):
        """Add rock type to Lithology.

        Parameters
        ----------
        attrs : dict
            Rock attribute dictionary for the new rock type(s).

        Examples
        --------
        >>> from landlab import RasterModelGrid
        >>> from landlab.components import Lithology
        >>> mg = RasterModelGrid(3, 3)
        >>> z = mg.add_zeros('node', 'topographic__elevation')
        >>> thicknesses = [1, 2, 4, 1]
        >>> ids = [1, 2, 1, 2]
        >>> attrs = {'K_sp': {1: 0.001,
        ...                   2: 0.0001}}
        >>> lith = Lithology(mg, thicknesses, ids, attrs)
        >>> lith.add_rock_type({'K_sp': {4: 0.03,
        ...                            6: 0.004}})
        >>> lith.ids
        frozenset({1, 2, 4, 6})
        >>> lith.properties
        {'K_sp': {1: 0.001, 2: 0.0001, 4: 0.03, 6: 0.004}}

        """
        # Check that the new rock type has all existing attributes
        for at in self._properties:
            if at not in attrs:
                msg = 'The new rock type is missing attribute ' + str(at) + '.'
                raise ValueError(msg)
        # And no new attributes
        for at in attrs:
            if at not in self._properties:
                msg = ('The new rock type has an attribute (e' + str(at) + ') '
                       'that no other rock type has. This is not permitted.')
                raise ValueError(msg)

        new_ids = []
        for at in attrs:
            att_dict = attrs[at]
            rids = att_dict.keys()
            for rid in rids:
                if rid in self._ids:
                    msg = ('Rock type ID ' + str(rid) + ' for attribute '
                           '' + str(at) + ' has already been added. This is '
                           'not allowed')
                    raise ValueError(msg)
                else:
                    new_ids.append(rid)
                    self._attrs[at][rid] = att_dict[rid]
        self.ids = self.ids.union(new_ids)

        # update surface values
        self._update_surface_values()

    def update_rock_properties(self, at, rock_id, value):
        """Update rock type attribute.

        Paramters
        ---------
        at : str
            Attribute name
        rock_id : value
            Rock type ID
        value : value
            New value for rock type attribute

        Examples
        --------
        >>> from landlab import RasterModelGrid
        >>> from landlab.components import Lithology
        >>> mg = RasterModelGrid(3, 3)
        >>> z = mg.add_zeros('node', 'topographic__elevation')
        >>> thicknesses = [1, 2, 4, 1]
        >>> ids = [1, 2, 1, 2]
        >>> attrs = {'K_sp': {1: 0.001,
        ...                   2: 0.0001}}
        >>> lith = Lithology(mg, thicknesses, ids, attrs)

        >>> mg.at_node['K_sp']
        array([ 0.001,  0.001,  0.001,  0.001,  0.001,  0.001,  0.001,  0.001,
            0.001])

        >>> lith.update_rock_properties('K_sp', 1, 0.03)

        >>> mg.at_node['K_sp']
        array([ 0.03,  0.03,  0.03,  0.03,  0.03,  0.03,  0.03,  0.03,  0.03])

        """
        if at not in self._properties:
            msg = ('Lithology cannot update the value of ' + str(at) + 'as '
                   'this attribute does not exist.')
            raise ValueError(msg)

        if self.ids.issuperset([rock_id]) == False:
            msg = ('Lithology cannot update the value of rock type '
                   '' + str(rock_id) + 'for attribute ' + str(at) + ' as '
                   'this rock type is not yet defined.')
            raise ValueError(msg)

        # set the value in the attribute dictionary
        self._attrs[at][rock_id] = value

        # set the value in the layers object
        self._layers[at] = self._get_new_values(at)

        # update surface values
        self._update_surface_values()

    def _get_new_values(self, at):
        """Get new values for attribute."""
        out = []
        rk_type = self._layers['rock_type__id']
        for i in range(rk_type.shape[0]):
            out.append(list(map(self._attrs[at].get, rk_type[i, :])))
        return np.array(out)

    def run_one_step(self, dz_advection=0, rock_id=None):
        """Update Lithology.

        The ``run_one_step`` method calculates elevation change of the
        Lithology surface (taking into account any advection due to external
        processes) and then either deposits or erodes based on elevation
        change.

        Parameters
        ----------
        dz_advenction : float or `(n_nodes, ) shape array, optional
            Change in rock elevation due to advection by some external process.
        rock_id : value or `(n_nodes, ) shape array, optional
            Rock type id for new material if deposited.

        Examples
        --------
        >>> from landlab import RasterModelGrid
        >>> from landlab.components import Lithology
        >>> mg = RasterModelGrid(3, 3)
        >>> z = mg.add_ones('node', 'topographic__elevation')
        >>> thicknesses = [1, 2, 4, 1]
        >>> ids = [1, 2, 1, 2]
        >>> attrs = {'K_sp': {1: 0.001,
        ...                   2: 0.0001}}
        >>> lith = Lithology(mg, thicknesses, ids, attrs)
        >>> lith.thickness
        array([ 8.,  8.,  8.,  8.,  8.,  8.,  8.,  8.,  8.])

        If we erode the surface, and then update Lithology, the thickness will
        change.

        >>> z -= 0.5
        >>> lith.run_one_step(dz_advection=0)
        >>> lith.thickness
        array([ 7.5,  7.5,  7.5,  7.5,  7.5,  7.5,  7.5,  7.5,  7.5])

        If you deposit, a valid rock_id must be provided

        >>> z += 1.5
        >>> lith.run_one_step(dz_advection=0, rock_id = 1)
        >>> lith.thickness
        array([ 9.,  9.,  9.,  9.,  9.,  9.,  9.,  9.,  9.])

        The default of Lithology is to use MaterialLayers from the landlab
        layers submodule. This means that when we erode, we will remove a layer
        from the layers datastructure if it has no material anywhere.

        """
        # calculate amount of erosion
        elevation_change = (self._grid['node']['topographic__elevation'] -
                            (self.last_elevation + dz_advection))

        # add layer
        self.add_layer(elevation_change, rock_id=rock_id)

        # update the last elevation.
        self.last_elevation = self._grid['node']['topographic__elevation'][:].copy()