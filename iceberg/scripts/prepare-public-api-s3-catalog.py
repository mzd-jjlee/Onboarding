"""Create only the MinIO-backed namespace through HMS. Existing namespaces stay unchanged."""
from pyiceberg.catalog import load_catalog

LOCATION = 's3a://lakehouse/warehouse/public_api_s3.db'

catalog = load_catalog('hive', type='hive', uri='thrift://hms:9083')
catalog.create_namespace_if_not_exists('public_api_s3', properties={'location': LOCATION})
found = catalog.load_namespace_properties('public_api_s3').get('location')
if found != LOCATION:
    raise SystemExit(f'public_api_s3 location is {found!r}, expected {LOCATION!r}; not loading')
print(f'public_api_s3 namespace ready at {found}; existing namespaces/tables unchanged')
