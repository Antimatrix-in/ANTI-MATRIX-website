from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

from .user import User
from .contact import ContactInquiry
from .job import JobPosting, JobApplication, Payment
from .employee import Employee
from .employee_onboarding_credential import EmployeeOnboardingCredential
from .document import DocumentTemplate, EmailTemplate, EmailTemplateMapping, EmployeeDocument, EmailLog
from .money_transaction import MoneyTransaction
from .internship_benefit import InternshipBenefit

# Alias for Offer Letter template management
OfferLetterTemplate = DocumentTemplate

__all__ = [
    'db', 'User', 'ContactInquiry', 'JobPosting', 'JobApplication',
    'Payment', 'Employee', 'EmployeeOnboardingCredential', 'DocumentTemplate', 'OfferLetterTemplate', 'EmailTemplate', 'EmailTemplateMapping', 'EmployeeDocument', 'EmailLog',
    'MoneyTransaction', 'InternshipBenefit'
]


