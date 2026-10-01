from datetime import date
from uuid import uuid4

import pytest

from app.models import AcademicHoliday, AcademicYear
from app.services.academic_calendar.service import (
    AcademicCalendarService,
    AcademicHolidayAlreadyExistsError,
    AcademicHolidayNotFoundError,
    AcademicYearAlreadyExistsError,
    ActiveAcademicYearNotFoundError,
)



from app.database import SessionLocal

@pytest.fixture(scope="function")
def db():
    session = SessionLocal()
    def clean_test_data():
        test_year = session.query(AcademicYear).filter(AcademicYear.name == "2026-2027").first()
        if test_year:
            session.query(AcademicHoliday).filter(AcademicHoliday.academic_year_id == test_year.id).delete(synchronize_session=False)
            session.delete(test_year)
            session.commit()

    try:
        clean_test_data()
        yield session
    finally:
        session.rollback()
        clean_test_data()
        session.close()
def test_create_academic_year(db):
    academic_year = AcademicCalendarService.create_academic_year(
        db,
        name="2026-2027",
        start_date=date(2026, 6, 1),
        end_date=date(2027, 5, 31),
    )

    assert academic_year.id is not None
    assert academic_year.name == "2026-2027"
    assert academic_year.start_date == date(2026, 6, 1)
    assert academic_year.end_date == date(2027, 5, 31)
    assert academic_year.is_active is True
    assert academic_year.data_origin == "PRODUCTION"

    db.commit()



def test_create_academic_year_rejects_invalid_date_range(db):
    with pytest.raises(ValueError, match="start_date must be before end_date"):
        AcademicCalendarService.create_academic_year(
            db,
            name="Invalid Year",
            start_date=date(2027, 5, 31),
            end_date=date(2026, 6, 1),
        )



def test_create_academic_year_rejects_duplicate_name(db):
    AcademicCalendarService.create_academic_year(
        db,
        name="2026-2027",
        start_date=date(2026, 6, 1),
        end_date=date(2027, 5, 31),
    )
    db.commit()

    with pytest.raises(AcademicYearAlreadyExistsError):
        AcademicCalendarService.create_academic_year(
            db,
            name="2026-2027",
            start_date=date(2026, 6, 1),
            end_date=date(2027, 5, 31),
        )

    db.rollback()


def test_get_active_academic_year(db):
    academic_year = AcademicCalendarService.create_academic_year(
        db,
        name="2026-2027",
        start_date=date(2026, 6, 1),
        end_date=date(2027, 5, 31),
        is_active=True,
    )
    db.commit()

    result = AcademicCalendarService.get_active_academic_year(db)

    assert result.id == academic_year.id
    assert result.is_active is True


def test_get_active_academic_year_when_none_exists(db):
    with pytest.raises(ActiveAcademicYearNotFoundError):
        AcademicCalendarService.get_active_academic_year(db)


def test_create_academic_holiday(db):
    academic_year = AcademicCalendarService.create_academic_year(
        db,
        name="2026-2027",
        start_date=date(2026, 6, 1),
        end_date=date(2027, 5, 31),
    )
    db.commit()

    holiday = AcademicCalendarService.create_academic_holiday(
        db,
        academic_year_id=academic_year.id,
        holiday_date=date(2026, 8, 15),
        name="Independence Day",
        type="NATIONAL",
        description="National holiday",
    )

    assert holiday.id is not None
    assert holiday.academic_year_id == academic_year.id
    assert holiday.holiday_date == date(2026, 8, 15)
    assert holiday.name == "Independence Day"
    assert holiday.type == "NATIONAL"
    assert holiday.description == "National holiday"
    assert holiday.is_active is True
    assert holiday.data_origin == "PRODUCTION"

    db.commit()


def test_create_academic_holiday_rejects_missing_academic_year(db):
    from app.services.academic_calendar.service import AcademicYearNotFoundError

    with pytest.raises(AcademicYearNotFoundError):
        AcademicCalendarService.create_academic_holiday(
            db,
            academic_year_id=uuid4(),
            holiday_date=date(2026, 8, 15),
            name="Independence Day",
            type="NATIONAL",
        )


def test_create_academic_holiday_rejects_duplicate_date(db):
    academic_year = AcademicCalendarService.create_academic_year(
        db,
        name="2026-2027",
        start_date=date(2026, 6, 1),
        end_date=date(2027, 5, 31),
    )
    db.commit()

    AcademicCalendarService.create_academic_holiday(
        db,
        academic_year_id=academic_year.id,
        holiday_date=date(2026, 8, 15),
        name="Independence Day",
        type="NATIONAL",
    )
    db.commit()

    with pytest.raises(AcademicHolidayAlreadyExistsError):
        AcademicCalendarService.create_academic_holiday(
            db,
            academic_year_id=academic_year.id,
            holiday_date=date(2026, 8, 15),
            name="Duplicate Holiday",
            type="OTHER",
        )

    db.rollback()


def test_list_active_holidays_ordered_by_date(db):
    academic_year = AcademicCalendarService.create_academic_year(
        db,
        name="2026-2027",
        start_date=date(2026, 6, 1),
        end_date=date(2027, 5, 31),
    )
    db.commit()

    late = AcademicCalendarService.create_academic_holiday(
        db,
        academic_year_id=academic_year.id,
        holiday_date=date(2026, 12, 25),
        name="Christmas",
        type="RELIGIOUS",
    )

    early = AcademicCalendarService.create_academic_holiday(
        db,
        academic_year_id=academic_year.id,
        holiday_date=date(2026, 8, 15),
        name="Independence Day",
        type="NATIONAL",
    )

    middle = AcademicCalendarService.create_academic_holiday(
        db,
        academic_year_id=academic_year.id,
        holiday_date=date(2026, 10, 2),
        name="Gandhi Jayanti",
        type="NATIONAL",
    )

    db.commit()

    holidays = AcademicCalendarService.list_holidays(
        db,
        academic_year.id,
    )

    assert [holiday.id for holiday in holidays] == [
        early.id,
        middle.id,
        late.id,
    ]


def test_list_holidays_can_include_inactive(db):
    academic_year = AcademicCalendarService.create_academic_year(
        db,
        name="2026-2027",
        start_date=date(2026, 6, 1),
        end_date=date(2027, 5, 31),
    )
    db.commit()

    active_holiday = AcademicCalendarService.create_academic_holiday(
        db,
        academic_year_id=academic_year.id,
        holiday_date=date(2026, 8, 15),
        name="Independence Day",
        type="NATIONAL",
    )

    inactive_holiday = AcademicCalendarService.create_academic_holiday(
        db,
        academic_year_id=academic_year.id,
        holiday_date=date(2026, 10, 2),
        name="Gandhi Jayanti",
        type="NATIONAL",
    )

    AcademicCalendarService.deactivate_holiday(
        db,
        inactive_holiday.id,
    )
    db.commit()

    active_only = AcademicCalendarService.list_holidays(
        db,
        academic_year.id,
    )

    assert [holiday.id for holiday in active_only] == [
        active_holiday.id
    ]

    all_holidays = AcademicCalendarService.list_holidays(
        db,
        academic_year.id,
        active_only=False,
    )

    assert [holiday.id for holiday in all_holidays] == [
        active_holiday.id,
        inactive_holiday.id,
    ]


def test_get_academic_holiday(db):
    academic_year = AcademicCalendarService.create_academic_year(
        db,
        name="2026-2027",
        start_date=date(2026, 6, 1),
        end_date=date(2027, 5, 31),
    )
    db.commit()

    holiday = AcademicCalendarService.create_academic_holiday(
        db,
        academic_year_id=academic_year.id,
        holiday_date=date(2026, 8, 15),
        name="Independence Day",
        type="NATIONAL",
    )
    db.commit()

    result = AcademicCalendarService.get_holiday(
        db,
        holiday.id,
    )

    assert result.id == holiday.id
    assert result.name == "Independence Day"


def test_get_academic_holiday_not_found(db):
    with pytest.raises(AcademicHolidayNotFoundError):
        AcademicCalendarService.get_holiday(
            db,
            uuid4(),
        )


def test_deactivate_academic_holiday(db):
    academic_year = AcademicCalendarService.create_academic_year(
        db,
        name="2026-2027",
        start_date=date(2026, 6, 1),
        end_date=date(2027, 5, 31),
    )
    db.commit()

    holiday = AcademicCalendarService.create_academic_holiday(
        db,
        academic_year_id=academic_year.id,
        holiday_date=date(2026, 8, 15),
        name="Independence Day",
        type="NATIONAL",
    )
    db.commit()

    result = AcademicCalendarService.deactivate_holiday(
        db,
        holiday.id,
    )

    assert result.id == holiday.id
    assert result.is_active is False

    db.commit()

    refreshed = (
        db.query(AcademicHoliday)
        .filter(AcademicHoliday.id == holiday.id)
        .one()
    )

    assert refreshed.is_active is False


def test_service_does_not_commit(db):
    academic_year = AcademicCalendarService.create_academic_year(
        db,
        name="2026-2027",
        start_date=date(2026, 6, 1),
        end_date=date(2027, 5, 31),
    )

    assert academic_year.id is not None

    # flush() makes the object/database row available inside the
    # current transaction, but the service must not commit it.
    assert (
        db.query(AcademicYear)
        .filter(AcademicYear.id == academic_year.id)
        .one()
        .name
        == "2026-2027"
    )

    db.rollback()

    assert (
        db.query(AcademicYear)
        .filter(AcademicYear.id == academic_year.id)
        .first()
        is None
    )


def test_update_holiday_preserves_identity_and_can_reactivate(db):
    academic_year = AcademicCalendarService.create_academic_year(
        db,
        name="2026-2027",
        start_date=date(2026, 6, 1),
        end_date=date(2027, 5, 31),
    )
    holiday = AcademicCalendarService.create_academic_holiday(
        db,
        academic_year_id=academic_year.id,
        holiday_date=date(2026, 8, 15),
        name="Independence Day",
        type="NATIONAL",
    )

    updated = AcademicCalendarService.update_holiday(
        db,
        holiday.id,
        holiday_date=date(2026, 8, 16),
        name="Observed Independence Day",
        is_active=False,
    )

    assert updated.id == holiday.id
    assert updated.holiday_date == date(2026, 8, 16)
    assert updated.name == "Observed Independence Day"
    assert updated.is_active is False

    reactivated = AcademicCalendarService.update_holiday(
        db,
        holiday.id,
        is_active=True,
    )
    assert reactivated.id == holiday.id
    assert reactivated.is_active is True


def test_calendar_range_must_be_inside_academic_year(db):
    academic_year = AcademicCalendarService.create_academic_year(
        db,
        name="2026-2027",
        start_date=date(2026, 6, 1),
        end_date=date(2027, 5, 31),
    )

    with pytest.raises(ValueError, match="within the academic year"):
        AcademicCalendarService.get_calendar_view(
            db,
            academic_year_id=academic_year.id,
            para_teacher_id=None,
            start_date=date(2026, 5, 31),
            end_date=date(2026, 6, 1),
        )


def test_planning_compliance_requires_monday(db):
    with pytest.raises(ValueError, match="must be a Monday"):
        AcademicCalendarService.evaluate_planning_compliance(
            db,
            week_start_date=date(2026, 7, 1),
        )





def test_aggregation_empty_range(db):
    from app.services.academic_calendar.service import AcademicCalendarService
    academic_year = AcademicCalendarService.create_academic_year(
        db, name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31)
    )
    db.commit()

    days = AcademicCalendarService.get_calendar_view(
        db,
        academic_year_id=academic_year.id,
        para_teacher_id=uuid4(),
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 3),
        current_date=date(2026, 7, 1)
    )

    assert len(days) == 3
    assert days[0].calendar_date == date(2026, 7, 1)
    assert days[0].is_holiday is False
    assert len(days[0].sessions) == 0

def test_aggregation_with_holiday_and_reschedule(db):
    from app.services.academic_calendar.service import AcademicCalendarService
    from app.models.session_plan_week import SessionPlanWeek
    from app.models.session_plan_item import SessionPlanItem
    from app.models.user import User
    from app.models.class_division import ClassDivision
    from app.models.school import School

    academic_year = AcademicCalendarService.create_academic_year(
        db, name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31)
    )
    holiday = AcademicCalendarService.create_academic_holiday(
        db, academic_year_id=academic_year.id, holiday_date=date(2026, 7, 2),
        name="Test Holiday", type="OTHER"
    )

    user_id = uuid4()
    u = User(id=user_id, user_code=f"U_{uuid4().hex[:6]}", full_name="T", email=f"{uuid4().hex[:6]}@t.com", password_hash="h")
    db.add(u)

    school_id = uuid4()
    s = School(id=school_id, school_name="S1", school_code=f"S_{uuid4().hex[:6]}")
    db.add(s)

    cd_id = uuid4()
    cd = ClassDivision(id=cd_id, school_id=school_id, class_level=5, division="A")
    db.add(cd)

    spw_id = uuid4()
    spw = SessionPlanWeek(id=spw_id, para_teacher_id=user_id, week_start_date=date(2026, 6, 29), week_end_date=date(2026, 7, 5))
    db.add(spw)

    # Session 1: On normal day (future)
    spi1 = SessionPlanItem(session_plan_week_id=spw_id, class_division_id=cd_id, planned_date=date(2026, 7, 3), sequence_no=1)
    db.add(spi1)

    # Session 2: On holiday
    spi2 = SessionPlanItem(session_plan_week_id=spw_id, class_division_id=cd_id, planned_date=date(2026, 7, 2), sequence_no=2)
    db.add(spi2)

    # Session 3: Past due
    spi3 = SessionPlanItem(session_plan_week_id=spw_id, class_division_id=cd_id, planned_date=date(2026, 7, 1), sequence_no=3)
    db.add(spi3)

    db.commit()

    days = AcademicCalendarService.get_calendar_view(
        db, academic_year_id=academic_year.id, para_teacher_id=user_id,
        start_date=date(2026, 7, 1), end_date=date(2026, 7, 3), current_date=date(2026, 7, 2)
    )

    assert len(days) == 3

    # 7/1: past due -> RESCHEDULE_REQUIRED
    assert days[0].calendar_date == date(2026, 7, 1)
    assert days[0].sessions[0].derived_status == "RESCHEDULE_REQUIRED"

    # 7/2: holiday -> RESCHEDULE_REQUIRED
    assert days[1].calendar_date == date(2026, 7, 2)
    assert days[1].is_holiday is True
    assert days[1].sessions[0].derived_status == "RESCHEDULE_REQUIRED"

    # 7/3: future -> PLANNED
    assert days[2].calendar_date == date(2026, 7, 3)
    assert days[2].sessions[0].derived_status == "PLANNED"
