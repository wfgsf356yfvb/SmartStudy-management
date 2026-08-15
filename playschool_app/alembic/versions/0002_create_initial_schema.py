"""Create tenant initial schema

Revision ID: 0002_create_initial_schema
Revises: 0001_initial_schema
Create Date: 2026-08-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '0002_create_initial_schema'
down_revision = '0001_initial_schema'
branch_labels = None
depend_on = None


def upgrade():
    # Users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=150), nullable=False, unique=True),
        sa.Column('phone', sa.String(length=15), nullable=True),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('role', sa.Enum('super_admin','admin','teacher','student', name='role_enum'), nullable=False, server_default='student'),
        sa.Column('class_level', sa.Enum('nursery','lkg','ukg', name='class_level_enum'), nullable=True),
        sa.Column('parent_name', sa.String(length=100), nullable=True),
        sa.Column('parent_phone', sa.String(length=15), nullable=True),
        sa.Column('profile_pic', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4'
    )

    # Homework table
    op.create_table(
        'homework',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('teacher_id', sa.Integer, nullable=False),
        sa.Column('class_level', sa.Enum('nursery','lkg','ukg','all', name='homework_class_enum'), nullable=False, server_default='all'),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('file_path', sa.String(length=255), nullable=True),
        sa.Column('homework_type', sa.Enum('drawing','writing','reading','coloring','activity','other', name='homework_type_enum'), nullable=False, server_default='other'),
        sa.Column('due_date', sa.Date, nullable=False),
        sa.Column('max_marks', sa.Integer, nullable=False, server_default='10'),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4'
    )

    # Submissions table
    op.create_table(
        'submissions',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('homework_id', sa.Integer, nullable=False),
        sa.Column('student_id', sa.Integer, nullable=False),
        sa.Column('file_path', sa.String(length=255), nullable=True),
        sa.Column('remarks', sa.Text, nullable=True),
        sa.Column('submitted_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('marks', sa.Integer, nullable=True),
        sa.Column('grade', sa.String(length=5), nullable=True),
        sa.Column('feedback', sa.Text, nullable=True),
        sa.Column('graded_at', sa.TIMESTAMP(), nullable=True),
        sa.UniqueConstraint('homework_id', 'student_id', name='unique_submission'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4'
    )

    # Weekly progress
    op.create_table(
        'weekly_progress',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('student_id', sa.Integer, nullable=False),
        sa.Column('teacher_id', sa.Integer, nullable=False),
        sa.Column('week_number', sa.Integer, nullable=False),
        sa.Column('year', sa.Integer, nullable=False),
        sa.Column('subject', sa.String(length=50), nullable=False, server_default='Overall'),
        sa.Column('marks_obtained', sa.Numeric(5,2), nullable=False, server_default='0'),
        sa.Column('total_marks', sa.Numeric(5,2), nullable=False, server_default='100'),
        sa.Column('grade', sa.String(length=5), nullable=True),
        sa.Column('teacher_remarks', sa.Text, nullable=True),
        sa.Column('parent_notified', sa.Boolean, nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4'
    )

    # Game scores
    op.create_table(
        'game_scores',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('student_id', sa.Integer, nullable=False),
        sa.Column('game_name', sa.String(length=100), nullable=False),
        sa.Column('score', sa.Integer, nullable=False, server_default='0'),
        sa.Column('stars', sa.Integer, nullable=False, server_default='0'),
        sa.Column('played_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4'
    )

    # Announcements
    op.create_table(
        'announcements',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('author_id', sa.Integer, nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('target_role', sa.Enum('all','teacher','student', name='announcement_role_enum'), nullable=False, server_default='all'),
        sa.Column('target_class', sa.Enum('all','nursery','lkg','ukg', name='announcement_class_enum'), nullable=False, server_default='all'),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4'
    )


def downgrade():
    op.drop_table('announcements')
    op.drop_table('game_scores')
    op.drop_table('weekly_progress')
    op.drop_table('submissions')
    op.drop_table('homework')
    op.drop_table('users')
    # Note: Enums will be removed automatically by Alembic/SQLAlchemy in many setups; if not, manual cleanup may be required.
