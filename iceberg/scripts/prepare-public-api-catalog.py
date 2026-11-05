"""Create only the namespace for the public API lab through HMS."""
from pyiceberg.catalog import load_catalog

catalog = load_catalog('hive', type='hive', uri='thrift://hms:9083')
catalog.create_namespace_if_not_exists(
    'public_api', properties={'location': 'file:///lake/warehouse/public_api.db'}
)
print('public_api namespace ready; existing namespaces/tables unchanged')
