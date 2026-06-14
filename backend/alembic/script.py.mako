<%!
from alembic import util
%>
"""${message}
Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from alembic import op
import sqlalchemy as sa

${imports if imports else ''}


def upgrade():
%for upgrade_stmt in upgrade_ops:
    ${upgrade_stmt}
%endfor


def downgrade():
%for downgrade_stmt in downgrade_ops:
    ${downgrade_stmt}
%endfor
