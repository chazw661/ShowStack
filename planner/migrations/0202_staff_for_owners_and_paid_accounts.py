"""Give admin access (is_staff) to every project owner and paid/beta account.

The equipment pages, "+ Create New Project" and the Admin Panel button are
all in the admin, which needs is_staff. Only accepting an invitation ever set
it, so a paid or beta owner who had never been invited to someone else's show
could not open their own. planner.signals now sets it going forward; this
does the accounts that already exist.

Grant-only, active accounts only, and nothing else on the row changes. No
reverse: un-staffing people on a rollback would lock out owners who were
staffed by hand before this ran, and there is no telling them apart.
"""

from django.db import migrations
from django.db.models import Q


def grant(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    Project = apps.get_model('planner', 'Project')
    owners = Project.objects.values('owner_id')
    users = User.objects.filter(is_active=True, is_staff=False).filter(
        Q(pk__in=owners) | Q(userprofile__account_type__in=('paid', 'beta')))
    count = users.update(is_staff=True)
    if count:
        print(f'\n  [0202] gave admin access to {count} owner/paid/beta account(s)')


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('planner', '0201_show_templates'),
    ]

    operations = [
        migrations.RunPython(grant, migrations.RunPython.noop),
    ]
