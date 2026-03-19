"""Harden tenant integrity with DB-level org constraints.

Revision ID: 20260318_0014
Revises: 20260318_0013
Create Date: 2026-03-18 22:10:00.000000
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260318_0014"
down_revision = "20260318_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user") as batch_op:
        batch_op.create_unique_constraint("uq_user_id_org", ["id", "o_id"])

    with op.batch_alter_table("role") as batch_op:
        batch_op.create_unique_constraint("uq_role_id_org", ["id", "o_id"])

    with op.batch_alter_table("event_labels") as batch_op:
        batch_op.create_unique_constraint("uq_event_labels_el_id_o_id", ["el_id", "o_id"])

    op.execute("ALTER TABLE testing_record_log DROP CONSTRAINT IF EXISTS testing_record_log_el_id_fkey")
    with op.batch_alter_table("testing_record_log") as batch_op:
        batch_op.create_foreign_key(
            "fk_testing_record_log_label_org",
            "event_labels",
            ["el_id", "o_id"],
            ["el_id", "o_id"],
        )

    with op.batch_alter_table("roles_users") as batch_op:
        batch_op.create_unique_constraint("uq_roles_users_user_role", ["user_id", "role_id"])

    op.execute(
        """
        CREATE OR REPLACE FUNCTION verify_roles_users_same_org()
        RETURNS trigger AS $$
        DECLARE
            user_org integer;
            role_org integer;
        BEGIN
            SELECT o_id INTO user_org FROM "user" WHERE id = NEW.user_id;
            SELECT o_id INTO role_org FROM role WHERE id = NEW.role_id;

            IF user_org IS NULL OR role_org IS NULL THEN
                RAISE EXCEPTION
                    USING MESSAGE = 'roles_users references a missing user or role',
                          ERRCODE = '23503';
            END IF;

            IF user_org <> role_org THEN
                RAISE EXCEPTION
                    USING MESSAGE = 'roles_users links a user and role from different organisations',
                          ERRCODE = '23514';
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_roles_users_same_org
        BEFORE INSERT OR UPDATE ON roles_users
        FOR EACH ROW
        EXECUTE FUNCTION verify_roles_users_same_org();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_roles_users_same_org ON roles_users")
    op.execute("DROP FUNCTION IF EXISTS verify_roles_users_same_org()")

    with op.batch_alter_table("roles_users") as batch_op:
        batch_op.drop_constraint("uq_roles_users_user_role", type_="unique")

    with op.batch_alter_table("testing_record_log") as batch_op:
        batch_op.drop_constraint("fk_testing_record_log_label_org", type_="foreignkey")
        batch_op.create_foreign_key("testing_record_log_el_id_fkey", "event_labels", ["el_id"], ["el_id"])

    with op.batch_alter_table("event_labels") as batch_op:
        batch_op.drop_constraint("uq_event_labels_el_id_o_id", type_="unique")

    with op.batch_alter_table("role") as batch_op:
        batch_op.drop_constraint("uq_role_id_org", type_="unique")

    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_constraint("uq_user_id_org", type_="unique")
