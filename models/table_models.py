"""
models.py  –  SQLAlchemy 2.x declarative models
for the MAB Intelligence Procurement-Audit Platform.

Style intentionally matches the reference snippet you provided
(no mix-ins, explicit Column definitions, classic `declarative_base`).
"""
from __future__ import annotations

from datetime import datetime, date, timedelta
import enum

from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Boolean,
    DateTime, Date, Interval, Numeric,
    ForeignKey, JSON, Index, UniqueConstraint,
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# ──────────────────────────────────────────────
# ENUM DEFINITIONS
# ──────────────────────────────────────────────
class PermissionLevel(enum.Enum):
    view = "view"
    edit = "edit"
    manage = "manage"
    no_access = "no_access"


class ProjectStatus(enum.Enum):
    draft = "draft"
    active = "active"
    completed = "completed"
    pending = "pending"
    in_progress = "in_progress"


class JobStatus(enum.Enum):
    uploaded = "uploaded"
    processing = "processing"
    processed = "processed"
    validated = "validated"
    analyzing = "analyzing"
    completed = "completed"
    failed = "failed"

# ──────────────────────────────────────────────
# PERMISSIONS MATRIX
# ──────────────────────────────────────────────
class Permission(Base):
    __tablename__ = "permissions"

    id              = Column(Integer, primary_key=True)
    organization    = Column(SQLEnum(PermissionLevel, name="permission_level"), nullable=False)
    team            = Column(SQLEnum(PermissionLevel, name="permission_level"), nullable=False)
    projects        = Column(SQLEnum(PermissionLevel, name="permission_level"), nullable=False)
    sheets          = Column(SQLEnum(PermissionLevel, name="permission_level"), nullable=False)
    analysis        = Column(SQLEnum(PermissionLevel, name="permission_level"), nullable=False)
    file_processing = Column(SQLEnum(PermissionLevel, name="permission_level"), nullable=False)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime)

# ──────────────────────────────────────────────
# ROLES & USERS
# ──────────────────────────────────────────────
class Role(Base):
    __tablename__ = "roles"

    id          = Column(Integer, primary_key=True)
    name        = Column(String(50), unique=True, nullable=False)
    description = Column(Text)
    is_active   = Column(Boolean, default=True)
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime)
    deleted_at  = Column(DateTime)

    users = relationship("User", back_populates="role")


class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True)
    email         = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255))
    full_name     = Column(String(255))
    designation   = Column(String(255), nullable=True)
    image         = Column(String(512), nullable=True)
    role_id       = Column(Integer, ForeignKey("roles.id"))
    is_active     = Column(Boolean, default=True)
    last_login_at = Column(DateTime)
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at    = Column(DateTime)

    role          = relationship("Role", back_populates="users")
    # org / team / object junctions (declared later) back-populate here
    orgs_assoc    = relationship("UserOrganization", back_populates="user", cascade="all, delete-orphan")
    teams_assoc   = relationship("UserTeam",         back_populates="user", cascade="all, delete-orphan")
    projects_assoc= relationship("UserProject",      back_populates="user", cascade="all, delete-orphan")
    sheets_assoc  = relationship("UserSheet",        back_populates="user", cascade="all, delete-orphan")
    analysis_assoc= relationship("UserAnalysis",     back_populates="user", cascade="all, delete-orphan")
    files_assoc   = relationship("UserFileProcessing", back_populates="user", cascade="all, delete-orphan")

# ──────────────────────────────────────────────
# ORGANISATIONS & TEAMS
# ──────────────────────────────────────────────
class Organization(Base):
    __tablename__ = "organizations"

    id                 = Column(Integer, primary_key=True)
    name               = Column(String(100), unique=True, nullable=False)
    description        = Column(Text)
    organisation_admin = Column(Integer, ForeignKey("users.id"), nullable=True)
    email = Column(String, nullable=True)
    permission_id      = Column(Integer, ForeignKey("permissions.id"), nullable=True)
    is_active          = Column(Boolean, default=True)
    created_at         = Column(DateTime, default=datetime.utcnow)
    updated_at         = Column(DateTime)
    created_by         = Column(Integer, ForeignKey("users.id"))
    updated_by         = Column(Integer, ForeignKey("users.id"))
    deleted_at         = Column(DateTime)

    admin        = relationship("User", foreign_keys=[organisation_admin])
    permission   = relationship("Permission")
    creator      = relationship("User", foreign_keys=[created_by])
    updater      = relationship("User", foreign_keys=[updated_by])

    teams        = relationship("Team", back_populates="organization", cascade="all, delete-orphan")
    users_assoc  = relationship("UserOrganization", back_populates="organization", cascade="all, delete-orphan")


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_teams_org_name"),
        Index("ix_teams_org_active", "org_id", "is_active"),
    )

    id            = Column(Integer, primary_key=True)
    name          = Column(String(100), nullable=False)
    org_id        = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    description   = Column(Text)
    permission_id = Column(Integer, ForeignKey("permissions.id"))
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=datetime.utcnow)
    created_by    = Column(Integer, ForeignKey("users.id"))
    updated_at    = Column(DateTime)
    updated_by    = Column(Integer, ForeignKey("users.id"))
    deleted_at    = Column(DateTime)

    organization  = relationship("Organization", back_populates="teams")
    permission    = relationship("Permission")
    creator       = relationship("User", foreign_keys=[created_by])
    updater       = relationship("User", foreign_keys=[updated_by])

    users_assoc   = relationship("UserTeam", back_populates="team", cascade="all, delete-orphan")
    projects      = relationship("Project", back_populates="team", cascade="all, delete-orphan")

# ──────────────────────────────────────────────
# USER ↔ ORG / TEAM / PROJECT / SHEET / FILE PERMISSIONS
# ──────────────────────────────────────────────
class UserOrganization(Base):
    __tablename__ = "user_organizations"
    __table_args__ = (
        Index("ix_user_orgs_org_id", "organization_id"),
    )

    user_id         = Column(Integer, ForeignKey("users.id"), primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), primary_key=True)
    permission_id   = Column(Integer, ForeignKey("permissions.id"))
    is_admin        = Column(Boolean, default=False)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user         = relationship("User", back_populates="orgs_assoc")
    organization = relationship("Organization", back_populates="users_assoc")
    permission   = relationship("Permission")


class UserTeam(Base):
    __tablename__ = "user_teams"
    __table_args__ = (
        Index("ix_user_teams_team_id", "team_id"),
    )

    user_id       = Column(Integer, ForeignKey("users.id"), primary_key=True)
    team_id       = Column(Integer, ForeignKey("teams.id"), primary_key=True)
    permission_id = Column(Integer, ForeignKey("permissions.id"))
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime)

    user       = relationship("User", back_populates="teams_assoc")
    team       = relationship("Team", back_populates="users_assoc")
    permission = relationship("Permission")


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_team_status", "team_id", "status"),
    )

    id          = Column(Integer, primary_key=True)
    name        = Column(String(100), nullable=False)
    description = Column(Text)
    team_id     = Column(Integer, ForeignKey("teams.id"), nullable=False)
    status      = Column(SQLEnum(ProjectStatus, name="project_status"), default=ProjectStatus.active, nullable=False, index=True)
    start_date  = Column(Date)
    end_date    = Column(Date)
    is_active   = Column(Boolean, default=True)
    space_link  = Column(String(512))  
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at  = Column(DateTime)

    team          = relationship("Team", back_populates="projects")
    project_files = relationship("ProjectFile", back_populates="project", cascade="all, delete-orphan")
    users_assoc   = relationship("UserProject", back_populates="project", cascade="all, delete-orphan")
    analysis_assoc= relationship("UserAnalysis", back_populates="project", cascade="all, delete-orphan")
    file_metadata = relationship("FileMetadata", back_populates="project", cascade="all, delete-orphan")


class UserProject(Base):
    __tablename__ = "user_projects"
    __table_args__ = (
        Index("ix_user_projects_project_id", "project_id"),
    )

    user_id       = Column(Integer, ForeignKey("users.id"), primary_key=True)
    project_id    = Column(Integer, ForeignKey("projects.id"), primary_key=True)
    permission_id = Column(Integer, ForeignKey("permissions.id"))
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime)

    user       = relationship("User", back_populates="projects_assoc")
    project    = relationship("Project", back_populates="users_assoc")
    permission = relationship("Permission")


class UserAnalysis(Base):
    __tablename__ = "user_analysis"
    __table_args__ = (
        Index("ix_user_analysis_project_id", "project_id"),
    )

    user_id       = Column(Integer, ForeignKey("users.id"), primary_key=True)
    project_id    = Column(Integer, ForeignKey("projects.id"), primary_key=True)
    permission_id = Column(Integer, ForeignKey("permissions.id"))
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime)

    user       = relationship("User", back_populates="analysis_assoc")
    project    = relationship("Project", back_populates="analysis_assoc")
    permission = relationship("Permission")


# ──────────────────────────────────────────────
# FILES & METADATA
# ──────────────────────────────────────────────
class ProjectFile(Base):
    __tablename__ = "project_files"
    __table_args__ = (
        Index("ix_project_files_name_id", "file_name", "file_id"),
    )

    file_id             = Column(Integer, primary_key=True)
    file_name           = Column(String(500), nullable=False)
    storage_id          = Column(Integer, unique=True, nullable=False)
    status              = Column(String(50), nullable=False, index=True)
    processing_attempts = Column(Integer, default=0)
    text                = Column(String(500))
    uploaded_at         = Column(DateTime)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project_id          = Column(Integer, ForeignKey("projects.id"), nullable=False)
    project             = relationship("Project", back_populates="project_files")


class FileMetadata(Base):
    __tablename__ = "file_metadata"
    __table_args__ = (
        Index("ix_file_meta_proj_status", "project_id", "status"),
        Index("ix_file_meta_status", "status"),
        Index("ix_file_meta_created", "created_at"),
    )

    id                  = Column(BigInteger, primary_key=True)
    project_id          = Column(Integer, ForeignKey("projects.id"), nullable=False)
    original_filename   = Column(String(255), nullable=False)
    storage_path        = Column(String(512), nullable=False)
    file_size_bytes     = Column(BigInteger)
    content_type        = Column(String(100))
    sheet_count         = Column(Integer, default=1)
    status              = Column(String(50), default="uploaded", nullable=False)
    processing_attempts = Column(Integer, default=0)
    error_message       = Column(Text)
    file_mapping_column = Column(JSONB, nullable=True)
    uploaded_at         = Column(DateTime, default=datetime.utcnow)
    processed_at        = Column(DateTime)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime)
    deleted_at          = Column(DateTime)
    is_processed        = Column(Boolean, default=False)
    processed_path      = Column(String(512), nullable=True)
    file_hash           = Column(String(64), nullable=True, index=True)  # SHA-256 hash (64 chars)
    
    project         = relationship("Project", back_populates="file_metadata")
    file_sheets     = relationship("FileSheet", back_populates="file_meta", cascade="all, delete-orphan")
    files_assoc     = relationship("UserFileProcessing", back_populates="file_meta", cascade="all, delete-orphan")
    processing_jobs = relationship("ProcessingJob", back_populates="file", cascade="all, delete-orphan")


class SheetType(Base):
    __tablename__ = "sheet_types"

    id               = Column(Integer, primary_key=True)
    name             = Column(String(100), unique=True, nullable=False)
    description      = Column(Text)
    created_at       = Column(DateTime, default=datetime.utcnow)
    updated_at       = Column(DateTime)


class RetentionPolicy(Base):
    __tablename__ = "retention_policies"
    __table_args__ = (
        Index("ix_retention_policies_active", "is_active"),
    )

    id               = Column(Integer, primary_key=True)
    name             = Column(String(100), unique=True, nullable=False)
    description      = Column(Text)
    retention_period = Column(Interval, nullable=False)
    is_active        = Column(Boolean, default=True)
    created_at       = Column(DateTime, default=datetime.utcnow)
    updated_at       = Column(DateTime)
    created_by       = Column(Integer, ForeignKey("users.id"))
    updated_by       = Column(Integer, ForeignKey("users.id"))

    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])

# ──────────────────────────────────────────────
# FILE SHEETS
# ──────────────────────────────────────────────
class FileSheet(Base):
    __tablename__ = "file_sheets"
    __table_args__ = (
        UniqueConstraint("file_id", "sheet_name", name="uq_file_sheets_name"),
        UniqueConstraint("file_id", "sheet_index", name="uq_file_sheets_index"),
        Index("ix_file_sheets_status", "status"),
        Index("ix_file_sheets_type", "sheet_type_id"),
        Index("ix_file_sheets_retention", "retention_policy_id"),
        Index("ix_file_sheets_expiry", "retention_expiry_date"),
    )

    id                    = Column(Integer, primary_key=True)
    file_id               = Column(BigInteger, ForeignKey("file_metadata.id"), nullable=False)
    sheet_name            = Column(String(100), nullable=False)
    sheet_index           = Column(Integer, nullable=False)
    sheet_type_id         = Column(Integer, ForeignKey("sheet_types.id"))
    retention_policy_id   = Column(Integer, ForeignKey("retention_policies.id"))
    row_count             = Column(Integer)
    column_count          = Column(Integer)
    header_row_index      = Column(Integer, default=0)
    columns_metadata      = Column(JSONB)
    total_rows            = Column(Integer)
    processed_rows        = Column(Integer, default=0)
    status                = Column(String(50), default="pending", nullable=False)
    error_message         = Column(Text)
    last_processed_at     = Column(DateTime)
    retention_expiry_date = Column(Date)
    created_at            = Column(DateTime, default=datetime.utcnow)
    updated_at            = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    file_meta        = relationship("FileMetadata", back_populates="file_sheets")
    sheet_type       = relationship("SheetType")
    retention_policy = relationship("RetentionPolicy")
    sheets_assoc     = relationship("UserSheet", back_populates="sheet", cascade="all, delete-orphan")

# ──────────────────────────────────────────────
# USER-SHEET & USER-FILE
# ──────────────────────────────────────────────
class UserSheet(Base):
    __tablename__ = "user_sheets"
    __table_args__ = (
        Index("ix_user_sheets_sheet_id", "sheet_id"),
    )

    user_id       = Column(Integer, ForeignKey("users.id"), primary_key=True)
    sheet_id      = Column(Integer, ForeignKey("file_sheets.id"), primary_key=True)
    permission_id = Column(Integer, ForeignKey("permissions.id"))
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime)

    user       = relationship("User", back_populates="sheets_assoc")
    sheet      = relationship("FileSheet", back_populates="sheets_assoc")
    permission = relationship("Permission")


class UserFileProcessing(Base):
    __tablename__ = "user_file_processing"
    __table_args__ = (
        Index("ix_user_file_proc_file_id", "file_id"),
    )

    user_id       = Column(Integer, ForeignKey("users.id"), primary_key=True)
    file_id       = Column(BigInteger, ForeignKey("file_metadata.id"), primary_key=True)
    permission_id = Column(Integer, ForeignKey("permissions.id"))
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime)

    user       = relationship("User", back_populates="files_assoc")
    file_meta  = relationship("FileMetadata", back_populates="files_assoc")
    permission = relationship("Permission")

# ──────────────────────────────────────────────
# PROCESSING → STATS & HISTORY
# ──────────────────────────────────────────────
class ProcessingRecord(Base):
    __tablename__ = "processing_records"
    __table_args__ = (
        Index("ix_processing_records_sheet", "sheet_id"),
        Index("ix_processing_records_status", "status"),
    )

    id               = Column(Integer, primary_key=True)
    sheet_id         = Column(Integer, ForeignKey("file_sheets.id"), nullable=False)
    status           = Column(String(50), nullable=False)
    processed_rows   = Column(Integer)
    total_rows       = Column(Integer)
    processing_stats = Column(JSONB)
    started_at       = Column(DateTime)
    completed_at     = Column(DateTime)

    sheet = relationship("FileSheet")


class ProcessingHistory(Base):
    __tablename__ = "processing_history"
    __table_args__ = (
        Index("ix_processing_history_sheet", "sheet_id"),
        Index("ix_processing_history_when", "processed_at"),
    )

    id               = Column(Integer, primary_key=True)
    sheet_id         = Column(Integer, ForeignKey("file_sheets.id"), nullable=False)
    processed_rows   = Column(Integer)
    total_rows       = Column(Integer)
    processing_stats = Column(JSONB)
    status           = Column(String(50), nullable=False)
    message          = Column(Text)
    processed_at     = Column(DateTime, default=datetime.utcnow)

    sheet = relationship("FileSheet")

# ──────────────────────────────────────────────
# COLUMN MAPPINGS
# ──────────────────────────────────────────────
class ColumnMapping(Base):
    __tablename__ = "column_mappings"
    __table_args__ = (
        UniqueConstraint("project_id", "sheet_id", "source_column", name="uq_colmap_source"),
        Index("ix_colmap_sheet_target", "sheet_id", "target_column"),
    )

    id              = Column(Integer, primary_key=True)
    sheet_id        = Column(Integer, ForeignKey("file_sheets.id"), nullable=False)
    project_id      = Column(Integer, ForeignKey("projects.id"), nullable=False)
    source_column   = Column(String(255), nullable=False)
    target_column   = Column(String(255), nullable=False)
    required_column = Column(String(255), nullable=False)
    data_type       = Column(String(50), nullable=False)
    is_validated    = Column(Boolean, default=False)  # Add this line
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime)
    created_by      = Column(Integer, ForeignKey("users.id"))
    updated_by      = Column(Integer, ForeignKey("users.id"))

    sheet   = relationship("FileSheet")
    project = relationship("Project")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])



class FileMapping(Base):
    """Maps files to different contexts/mappings"""
    __tablename__ = "file_mappings"
    
    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("file_metadata.id"), nullable=False)
    context_type = Column(String, nullable=False)  # e.g., "project", "sheet", etc.
    context_id = Column(Integer, nullable=False)  # ID within that context
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    file = relationship("FileMetadata", back_populates="mappings")
    
    # Add unique constraint to avoid duplicate mappings
    __table_args__ = (
        UniqueConstraint('file_id', 'context_type', 'context_id', name='uq_file_mapping'),
    )

# Update FileMetadata to establish the relationship
FileMetadata.mappings = relationship("FileMapping", back_populates="file", cascade="all, delete-orphan")


# ──────────────────────────────────────────────
# DOCUMENTS & ANALYSIS
# ──────────────────────────────────────────────
class SheetData(Base):
    __tablename__ = "sheet_data"
    __table_args__ = (
        Index("ix_sheet_data_sheet", "sheet_id"),
        Index("ix_sheet_data_project", "project_id"),  # New index for project_id
        Index("ix_sheet_data_number", "document_number"),
        Index("ix_sheet_data_date", "document_date"),
    )

    id              = Column(Integer, primary_key=True)
    sheet_id        = Column(Integer, ForeignKey("file_sheets.id"), nullable=False)
    project_id      = Column(Integer, ForeignKey("projects.id"), nullable=True)  # New column
    document_number = Column(String(100))
    document_date   = Column(Date)
    sheet_space_link = Column(String(512), nullable=True)  # New column
    data            = Column(JSONB)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime)
    deleted_at      = Column(DateTime)
    created_by      = Column(Integer, ForeignKey("users.id"))
    updated_by      = Column(Integer, ForeignKey("users.id"))

    sheet    = relationship("FileSheet")
    project  = relationship("Project", foreign_keys=[project_id])  # New relationship
    creator  = relationship("User", foreign_keys=[created_by])
    updater  = relationship("User", foreign_keys=[updated_by])
    mappings = relationship("DocumentMapped", back_populates="sheet_data", cascade="all, delete-orphan")
    results  = relationship("DocumentResult", back_populates="sheet_data", cascade="all, delete-orphan")


class DocumentMapped(Base):
    __tablename__ = "document_mapped"
    __table_args__ = (
        UniqueConstraint("document_id", "version", name="uq_docmap_version"),
        Index("ix_docmap_latest", "document_id", "is_latest"),
        Index("ix_docmap_created", "created_at"),
    )

    id          = Column(BigInteger, primary_key=True)
    document_id = Column(Integer, ForeignKey("sheet_data.id"), nullable=False)
    mapped_data = Column(JSONB, nullable=False)
    version     = Column(Integer, default=1)
    is_latest   = Column(Boolean, default=True)
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime)
    created_by  = Column(Integer, ForeignKey("users.id"))
    updated_by  = Column(Integer, ForeignKey("users.id"))

    sheet_data = relationship("SheetData", back_populates="mappings")
    creator    = relationship("User", foreign_keys=[created_by])
    updater    = relationship("User", foreign_keys=[updated_by])
    results    = relationship("DocumentResult", back_populates="document_mapped", cascade="all, delete-orphan")


class DocumentResult(Base):
    __tablename__ = "document_results"
    __table_args__ = (
        Index("ix_docres_mapped", "mapped_id"),
        Index("ix_docres_type", "result_type"),
        Index("ix_docres_anomaly", "is_anomaly"),
    )

    id             = Column(BigInteger, primary_key=True)
    sheet_id       = Column(Integer, ForeignKey("sheet_data.id"), nullable=False)
    mapped_id      = Column(BigInteger, ForeignKey("document_mapped.id"), nullable=False)
    result_type    = Column(String(50), nullable=False)
    result_data    = Column(JSONB, nullable=False)
    is_anomaly     = Column(Boolean, default=False)
    is_latest      = Column(Boolean, default=True)
    created_at     = Column(DateTime, default=datetime.utcnow)

    sheet_data       = relationship("SheetData", back_populates="results")
    document_mapped  = relationship("DocumentMapped", back_populates="results")

# ──────────────────────────────────────────────
# AUDIT LOGS
# ──────────────────────────────────────────────
class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
        Index("ix_audit_action", "action"),
        Index("ix_audit_user", "user_id"),
        Index("ix_audit_created", "created_at"),
    )

    id          = Column(BigInteger, primary_key=True)
    entity_type = Column(String(50), nullable=False)
    entity_id   = Column(BigInteger, nullable=False)
    action      = Column(String(50), nullable=False)
    old_value   = Column(JSONB)
    new_value   = Column(JSONB)
    user_id     = Column(Integer, ForeignKey("users.id"))
    created_at  = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    
    id = Column(Integer, primary_key=True)
    file_id = Column(Integer, ForeignKey("file_metadata.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    status = Column(SQLEnum(JobStatus), default=JobStatus.uploaded, nullable=False)
    sheet_name = Column(String(255), nullable=True)
    mapping_id = Column(Integer, ForeignKey("column_mappings.id"), nullable=True)
    result_path = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    analysis_type = Column(String, nullable=True)
    parameters = Column(JSON, nullable=True)  # Adjust type as needed
    result_url = Column(String, nullable=True)
    
    
    file = relationship("FileMetadata", back_populates="processing_jobs")
    project = relationship("Project", foreign_keys=[project_id])
    mapping = relationship("ColumnMapping", foreign_keys=[mapping_id])


class WorkingType(Base):
    __tablename__ = "working_types"

    id          = Column(Integer, primary_key=True)
    name        = Column(String(255), nullable=False)
    key         = Column(String(100), nullable=False, unique=True)
    category    = Column(String(100), nullable=False, index=True)
    description = Column(Text)
    is_active   = Column(Boolean, default=True)
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime)

    def __repr__(self):
        return f"<WorkingType(id={self.id}, name='{self.name}', category='{self.category}'>"
