from app.database import SessionLocal
from app.models import Permission, Role, RolePermission


ROLES = [
    {
        "name": "Platform Owner",
        "code": "PLATFORM_OWNER",
        "description": "Highest platform authority with full project access.",
    },
    {
        "name": "System Administrator",
        "code": "SYSTEM_ADMIN",
        "description": "Delegated administrator responsible for operational administration and sensitive approvals.",
    },
    {
        "name": "Data Manager",
        "code": "DATA_MANAGER",
        "description": "Manages operational project data, imports, corrections and exports.",
    },
    {
        "name": "Management",
        "code": "MANAGEMENT",
        "description": "Monitoring and reporting access across the project.",
    },
    {
        "name": "STEM Coordinator",
        "code": "STEM_COORDINATOR",
        "description": "Monitors school sessions and conducts field inspections.",
    },
    {
        "name": "Para-Teacher",
        "code": "PARA_TEACHER",
        "description": "Conducts assigned school sessions and records session data.",
    },
]


PERMISSIONS = [
    # User management
    ("View Users", "user.view", "user"),
    ("Create Users", "user.create", "user"),
    ("Update Users", "user.update", "user"),
    ("Disable Users", "user.disable", "user"),

    # Roles and permissions
    ("View Roles", "role.view", "role"),
    ("Create Roles", "role.create", "role"),
    ("Update Roles", "role.update", "role"),
    ("Manage Role Permissions", "role_permission.manage", "role"),

    # Schools
    ("View Schools", "school.view", "school"),
    ("Create Schools", "school.create", "school"),
    ("Update Schools", "school.update", "school"),

    # Classes / divisions
    ("View Classes", "class.view", "class"),
    ("Create Classes", "class.create", "class"),
    ("Update Classes", "class.update", "class"),

    # Students
    ("View Students", "student.view", "student"),
    ("Create Students", "student.create", "student"),
    ("Update Students", "student.update", "student"),
    ("Import Students", "student.import", "student"),

    # Academic calendar
    ("View Academic Calendar", "calendar.view", "calendar"),
    ("Manage Academic Calendar", "calendar.manage", "calendar"),

    # Teaching sessions
    ("View Sessions", "session.view", "session"),
    ("Create Sessions", "session.create", "session"),
    ("Update Sessions", "session.update", "session"),

    # Attendance
    ("View Attendance", "attendance.view", "attendance"),
    ("Record Attendance", "attendance.create", "attendance"),
    ("Update Attendance", "attendance.update", "attendance"),

    # Engagement
    ("View Engagement", "engagement.view", "engagement"),
    ("Record Engagement", "engagement.create", "engagement"),
    ("Update Engagement", "engagement.update", "engagement"),

    # TLM
    ("View TLM", "tlm.view", "tlm"),
    ("Manage TLM", "tlm.manage", "tlm"),

        # Session TLM
    ("View Session TLM", "session_tlm.view", "session_tlm"),
    ("Record Session TLM", "session_tlm.create", "session_tlm"),
    ("Update Session TLM", "session_tlm.update", "session_tlm"),
    ("Delete Session TLM", "session_tlm.delete", "session_tlm"),

    # Assessments
    ("View Assessments", "assessment.view", "assessment"),
    ("Import Assessments", "assessment.import", "assessment"),
    ("Update Assessments", "assessment.update", "assessment"),

    # Evidence
    ("View Evidence", "evidence.view", "evidence"),
    ("Capture Evidence", "evidence.capture", "evidence"),
    ("Download Evidence", "evidence.download", "evidence"),
    ("Approve Evidence Access", "evidence.approve", "evidence"),

    # Feedback
    ("View Feedback", "feedback.view", "feedback"),
    ("Create Feedback", "feedback.create", "feedback"),

    # Reports
    ("View Reports", "report.view", "report"),
    ("Export Reports", "report.export", "report"),

    # Audit
    ("View Audit Logs", "audit.view", "audit"),

    # Change requests
    ("Create Change Requests", "change_request.create", "change_request"),
    ("View Change Requests", "change_request.view", "change_request"),
    ("Approve Change Requests", "change_request.approve", "change_request"),
    ("Reject Change Requests", "change_request.reject", "change_request"),
]


# Permissions assigned to each role.
ROLE_PERMISSIONS = {
    "PLATFORM_OWNER": "ALL",

    "SYSTEM_ADMIN": {
        "user.view",
        "user.create",
        "user.update",
        "user.disable",
        "role.view",
        "role.create",
        "role.update",
        "role_permission.manage",
        "school.view",
        "school.create",
        "school.update",
        "class.view",
        "class.create",
        "class.update",
        "student.view",
        "student.create",
        "student.update",
        "student.import",
        "calendar.view",
        "calendar.manage",
        "session.view",
        "session.create",
        "session.update",
        "attendance.view",
        "attendance.create",
        "attendance.update",
        "engagement.view",
        "engagement.create",
        "engagement.update",
        "tlm.view",
        "tlm.manage",
        "session_tlm.view",
        "session_tlm.create",
        "session_tlm.update",
        "session_tlm.delete",
        "assessment.view",
        "assessment.import",
        "assessment.update",
        "evidence.view",
        "evidence.download",
        "evidence.approve",
        "feedback.view",
        "feedback.create",
        "report.view",
        "report.export",
        "audit.view",
        "change_request.create",
        "change_request.view",
        "change_request.approve",
        "change_request.reject",
    },

    "DATA_MANAGER": {
        "school.view",
        "school.create",
        "school.update",
        "class.view",
        "class.create",
        "class.update",
        "student.view",
        "student.create",
        "student.update",
        "student.import",
        "calendar.view",
        "session.view",
        "session.create",
        "session.update",
        "attendance.view",
        "attendance.create",
        "attendance.update",
        "engagement.view",
        "engagement.create",
        "engagement.update",
        "tlm.view",
        "tlm.manage",
        "session_tlm.view",
        "session_tlm.create",
        "session_tlm.update",
        "session_tlm.delete",
        "assessment.view",
        "assessment.import",
        "assessment.update",
        "evidence.view",
        "feedback.view",
        "report.view",
        "report.export",
        "change_request.create",
        "change_request.view",
    },

    "MANAGEMENT": {
        "school.view",
        "class.view",
        "student.view",
        "calendar.view",
        "session.view",
        "attendance.view",
        "engagement.view",
        "tlm.view",
        "session_tlm.view",
        "assessment.view",
        "evidence.view",
        "feedback.view",
        "report.view",
        "report.export",
    },

    "STEM_COORDINATOR": {
        "school.view",
        "class.view",
        "student.view",
        "calendar.view",
        "session.view",
        "attendance.view",
        "engagement.view",
        "tlm.view",
        "session_tlm.view",
        "assessment.view",
        "evidence.view",
        "evidence.capture",
        "feedback.view",
        "feedback.create",
        "report.view",
    },

    "PARA_TEACHER": {
        "school.view",
        "class.view",
        "student.view",
        "calendar.view",
        "session.view",
        "session.create",
        "session.update",
        "attendance.view",
        "attendance.create",
        "attendance.update",
        "engagement.view",
        "engagement.create",
        "engagement.update",
        "tlm.view",
        "session_tlm.view",
        "session_tlm.create",
        "session_tlm.update",
        "evidence.capture",
        "feedback.view",
        "feedback.create",
    },
}


def seed_roles():
    db = SessionLocal()

    try:
        # -------------------------
        # Seed permissions
        # -------------------------
        permission_map = {}

        for name, code, module in PERMISSIONS:
            permission = (
                db.query(Permission)
                .filter(Permission.code == code)
                .first()
            )

            if not permission:
                permission = Permission(
                    name=name,
                    code=code,
                    module=module,
                )
                db.add(permission)
                db.flush()

            permission_map[code] = permission

        # -------------------------
        # Seed roles
        # -------------------------
        role_map = {}

        for role_data in ROLES:
            role = (
                db.query(Role)
                .filter(Role.code == role_data["code"])
                .first()
            )

            if not role:
                role = Role(
                    name=role_data["name"],
                    code=role_data["code"],
                    description=role_data["description"],
                    is_system_role=True,
                )
                db.add(role)
                db.flush()

            role_map[role.code] = role

        # -------------------------
        # Map permissions to roles
        # -------------------------
        for role_code, permission_codes in ROLE_PERMISSIONS.items():
            role = role_map[role_code]

            if permission_codes == "ALL":
                selected_permissions = permission_map.values()
            else:
                selected_permissions = (
                    permission_map[code]
                    for code in permission_codes
                )

            existing_permission_ids = {
                rp.permission_id
                for rp in db.query(RolePermission)
                .filter(RolePermission.role_id == role.id)
                .all()
            }

            for permission in selected_permissions:
                if permission.id not in existing_permission_ids:
                    db.add(
                        RolePermission(
                            role_id=role.id,
                            permission_id=permission.id,
                        )
                    )

        db.commit()

        print("Role and permission seed completed successfully.")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed_roles()
