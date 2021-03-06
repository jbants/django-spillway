from django.core.files.storage import default_storage
from django.db import connection
from greenwich import srs

from spillway.compat import mapnik
from spillway import colors, query

def make_dbsource(**kwargs):
    """Returns a mapnik PostGIS or SQLite Datasource."""
    if 'spatialite' in connection.settings_dict.get('ENGINE'):
        kwargs.setdefault('file', connection.settings_dict['NAME'])
        return mapnik.SQLite(wkb_format='spatialite', **kwargs)
    names = (('dbname', 'NAME'), ('user', 'USER'),
             ('password', 'PASSWORD'), ('host', 'HOST'), ('port', 'PORT'))
    for mopt, dopt in names:
        val = connection.settings_dict.get(dopt)
        if val:
            kwargs.setdefault(mopt, val)
    return mapnik.PostGIS(**kwargs)

def build_map(querysets, tileform):
    data = tileform.cleaned_data if tileform.is_valid() else {}
    stylename = data.get('style')
    m = Map()
    m.zoom_bbox(data.get('bbox'))
    for queryset in querysets:
        layer = m.layer(queryset, stylename)
        if isinstance(layer, RasterLayer):
            layer.add_colorizer_stops(data.get('limits'))
    return m


class Map(object):
    mapfile = default_storage.path('map.xml')

    def __init__(self):
        m = mapnik.Map(256, 256)
        try:
            mapnik.load_map(m, str(self.mapfile))
        except RuntimeError:
            pass
        m.buffer_size = 128
        m.srs = '+init=epsg:3857'
        self.map = m

    def layer(self, queryset, stylename=None):
        cls = VectorLayer if hasattr(queryset, 'geojson') else RasterLayer
        layer = cls(queryset, style=stylename)
        try:
            style = self.map.find_style(layer.stylename)
        except KeyError:
            self.map.append_style(layer.stylename, layer.style())
        layer.styles.append(layer.stylename)
        self.map.layers.append(layer._layer)
        return layer

    def render(self, format, bbox=None):
        img = mapnik.Image(self.map.width, self.map.height)
        mapnik.render(self.map, img)
        return img.tostring(format)

    def zoom_bbox(self, bbox):
        if bbox and bbox.area:
            bbox.transform(self.map.srs)
            self.map.zoom_to_box(mapnik.Box2d(*bbox.extent))


class Layer(object):
    """Base class for a Mapnik layer."""

    def __init__(self, queryset, style=None):
        table = str(queryset.model._meta.db_table)
        field = query.geo_field(queryset)
        sref = srs.SpatialReference(query.get_srid(queryset))
        layer = mapnik.Layer(table, sref.proj4)
        layer.datasource = make_dbsource(
            table=table, geometry_field=field.name)
        self._layer = layer
        self.stylename = style or self._layer.name
        self._symbolizer = None

    def __getattr__(self, attr):
        return getattr(self._layer, attr)

    def style(self):
        """Returns a default Style."""
        style = mapnik.Style()
        rule = mapnik.Rule()
        self._symbolizer = self.symbolizer()
        rule.symbols.append(self._symbolizer)
        style.rules.append(rule)
        return style

    def symbolizer(self):
        raise NotImplementedError


class RasterLayer(Layer):
    """A Mapnik layer for raster data types."""

    def __init__(self, obj, band=1, style=None):
        self._rstore = obj
        layer = mapnik.Layer(
            str(obj), srs.SpatialReference(obj.srs).proj4)
        layer.datasource = mapnik.Gdal(file=obj.image.path, band=band)
        self._layer = layer
        self.stylename = style or 'Spectral_r'
        self._symbolizer = None

    def add_colorizer_stops(self, limits):
        rcolors = colors.colormap.get(self.stylename)
        if rcolors:
            bins = self._rstore.linear(limits, k=len(rcolors))
            symbolizer = self._symbolizer
            for value, color in zip(bins, rcolors):
                symbolizer.colorizer.add_stop(value, mapnik.Color(color))

    def symbolizer(self):
        symbolizer = mapnik.RasterSymbolizer()
        symbolizer.colorizer = mapnik.RasterColorizer(
            mapnik.COLORIZER_LINEAR, mapnik.Color(0, 0, 0, 0))
        return symbolizer


class VectorLayer(Layer):
    """A Mapnik layer for vector data types."""

    def symbolizer(self):
        symbolizers = {
            mapnik.DataGeometryType.Point: mapnik.PointSymbolizer,
            mapnik.DataGeometryType.LineString: mapnik.LineSymbolizer,
            mapnik.DataGeometryType.Polygon: mapnik.PolygonSymbolizer
        }
        return symbolizers.get(self._layer.datasource.geometry_type(),
                               mapnik.PolygonSymbolizer)()
