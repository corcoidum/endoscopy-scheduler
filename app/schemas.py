from datetime import date, time

from pydantic import BaseModel, Field


class AppointmentForm(BaseModel):
    chart_number: str = Field(min_length=1, max_length=40)
    patient_name: str = Field(min_length=1, max_length=80)
    sex: str
    age: int | None = None
    phone_last4: str | None = Field(default=None, max_length=4)
    appointment_date: date
    appointment_time: time
    endoscopy_type: str
    ultrasound_abdomen: bool = False
    ultrasound_thyroid: bool = False
    ultrasound_carotid: bool = False
    ultrasound_cardiac: bool = False
    sedation: bool = False
    preparation_status: str
    medication_check_required: bool = False
    bowel_prep_type: str | None = None
    guardian_notice: bool = False
    notes: str | None = None
    override_reason: str | None = None
    version: int | None = None
