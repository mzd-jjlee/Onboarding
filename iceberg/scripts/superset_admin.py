"""Create the local admin once without resetting existing users/passwords."""
import os
from superset.app import create_app
from superset import security_manager

app = create_app()
with app.app_context():
    username = os.environ['SUPERSET_ADMIN_USERNAME']
    if security_manager.find_user(username=username):
        print('Admin already exists; password unchanged.')
    else:
        user = security_manager.add_user(
            username=username, first_name='Local', last_name='Admin',
            email='admin@localhost.invalid', role=security_manager.find_role('Admin'),
            password=os.environ['SUPERSET_ADMIN_PASSWORD'],
        )
        if not user:
            raise RuntimeError('Admin creation failed')
        print('Local admin created.')
