"""Rebuild organization hierarchy: Department -> Center -> Team -> Member

Revision ID: rebuild_org_hierarchy
Revises: add_org_role_to_bindings
Create Date: 2026-03-19

Organization Structure:
- Department (部门): 按产品线划分，如云产品一部、云产品二部
- Center (中心): 部门下的中心，如计算中心、存储中心
- Team (组): 最小管理单位，有正组长和副组长
- Member (员工): 属于某个组

Management Relations (多对多):
- GM 分管多个中心
- 总监 分管多个组
- 组长/副组长 管理组
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "rebuild_org_hierarchy"
down_revision = "add_org_role_to_bindings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 创建中心表 (org_centers)
    op.create_table(
        "org_centers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("department_id", UUID(as_uuid=True), sa.ForeignKey("org_departments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_org_centers_department_id", "org_centers", ["department_id"])
    op.create_index("ix_org_centers_tenant_id", "org_centers", ["tenant_id"])

    # 2. 创建组表 (org_teams)
    op.create_table(
        "org_teams",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("center_id", UUID(as_uuid=True), sa.ForeignKey("org_centers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_org_teams_center_id", "org_teams", ["center_id"])
    op.create_index("ix_org_teams_tenant_id", "org_teams", ["tenant_id"])

    # 3. 修改 org_members 表：添加 team_id 和 member_role
    op.add_column("org_members", sa.Column("team_id", UUID(as_uuid=True), sa.ForeignKey("org_teams.id", ondelete="SET NULL"), nullable=True))
    op.add_column("org_members", sa.Column("member_role", sa.String(50), server_default="member", nullable=False))
    op.create_index("ix_org_members_team_id", "org_members", ["team_id"])
    # member_role: 'member', 'deputy_leader', 'leader', 'director', 'gm', 'platform_admin'

    # 4. 创建管理关系表 (org_management_relations) - 多对多关系
    op.create_table(
        "org_management_relations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        # 管理者
        sa.Column("manager_member_id", UUID(as_uuid=True), sa.ForeignKey("org_members.id", ondelete="CASCADE"), nullable=False),
        sa.Column("manager_role", sa.String(50), nullable=False),  # 'gm', 'director', 'leader', 'deputy_leader'
        # 被管理对象 (三选一)
        sa.Column("managed_department_id", UUID(as_uuid=True), sa.ForeignKey("org_departments.id", ondelete="CASCADE"), nullable=True),
        sa.Column("managed_center_id", UUID(as_uuid=True), sa.ForeignKey("org_centers.id", ondelete="CASCADE"), nullable=True),
        sa.Column("managed_team_id", UUID(as_uuid=True), sa.ForeignKey("org_teams.id", ondelete="CASCADE"), nullable=True),
        # 是否主要负责人 (正组长 vs 副组长)
        sa.Column("is_primary", sa.Boolean, server_default=sa.false(), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_org_mgmt_rel_manager", "org_management_relations", ["manager_member_id"])
    op.create_index("ix_org_mgmt_rel_dept", "org_management_relations", ["managed_department_id"])
    op.create_index("ix_org_mgmt_rel_center", "org_management_relations", ["managed_center_id"])
    op.create_index("ix_org_mgmt_rel_team", "org_management_relations", ["managed_team_id"])

    # 5. 创建用户-组织成员关联表 (user_org_member_links)
    op.create_table(
        "user_org_member_links",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_member_id", UUID(as_uuid=True), sa.ForeignKey("org_members.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_primary", sa.Boolean, server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_user_org_member_user", "user_org_member_links", ["user_id"])
    op.create_index("ix_user_org_member_member", "user_org_member_links", ["org_member_id"])
    op.create_unique_constraint("uq_user_org_member", "user_org_member_links", ["user_id", "org_member_id"])

    # 6. 为 org_departments 添加 description 字段 (如果不存在)
    op.add_column("org_departments", sa.Column("description", sa.Text, nullable=True))


def downgrade() -> None:
    # 删除新表和字段
    op.drop_table("user_org_member_links")
    op.drop_table("org_management_relations")
    op.drop_index("ix_org_members_team_id", table_name="org_members")
    op.drop_column("org_members", "member_role")
    op.drop_column("org_members", "team_id")
    op.drop_table("org_teams")
    op.drop_table("org_centers")
    op.drop_column("org_departments", "description")
