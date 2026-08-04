from .mixins import db


class GazetteerPlace(db.Model):
    """A known town/city/administrative-capital and its centroid
    coordinates, used by geocoding_service.py to resolve freeform location
    strings (User.location, Entity.location) to an approximate lat/lon via
    fuzzy string matching -- see docs/entity-geolocation.md.

    Seeded from a bundled GeoNames export (data/gazetteer/, CC BY 4.0) via
    the `flask gazetteer-load` CLI command, not created/edited through the
    app's own UI.
    """
    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.Integer, unique=True)  # GeoNames geonameid, for idempotent reloads
    name = db.Column(db.String(200), nullable=False)
    normalized_name = db.Column(db.String(200), nullable=False, index=True)  # lowercased/stripped, fast-path lookup
    admin_region = db.Column(db.String(100))  # raw admin1 code, e.g. "AK" -- see data/gazetteer/README.md
    country_code = db.Column(db.String(2))
    feature_type = db.Column(db.String(20))  # raw GeoNames feature code, e.g. "PPLA2", "PPLC"
    population = db.Column(db.Integer)  # tie-breaking signal when multiple candidates match equally well
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'admin_region': self.admin_region,
            'country_code': self.country_code,
            'latitude': self.latitude,
            'longitude': self.longitude,
        }
