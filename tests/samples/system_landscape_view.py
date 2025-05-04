# Example slightly stolen from: https://c4model.com/diagrams/system-landscape

import buildzr
from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Person,
    Container,
    SystemLandscapeView,
)
from ..abstract_builder import AbstractBuilder

class SystemLandscapeViewSample(AbstractBuilder):

    def build(self) -> buildzr.models.Workspace:
        with Workspace('w', scope='landscape') as w:
            personal_banking_customer = Person('Personal Banking Customer')
            customer_service_staff = Person('Customer Service Staff')
            back_office_staff = Person('Back Office Staff')
            atm = SoftwareSystem('ATM')
            internet_banking_system = SoftwareSystem('Internet Banking System')
            email_system = SoftwareSystem('Email System')
            mainframe_banking_system = SoftwareSystem('Mainframe Banking System')

            personal_banking_customer >> "Withdraws cash using" >> atm
            personal_banking_customer >> "Views account balance, and makes payments using" >> internet_banking_system
            email_system >> "Sends e-mail to" >> personal_banking_customer
            personal_banking_customer >> "Ask questions to" >> customer_service_staff
            customer_service_staff >> "Uses" >> mainframe_banking_system
            back_office_staff >> "Uses" >> mainframe_banking_system
            atm >> "Uses" >> mainframe_banking_system
            internet_banking_system >> "Gets account information from, and makes payments using" >> mainframe_banking_system
            internet_banking_system >> "Sends e-mail using" >> email_system

            w.apply_views(
                SystemLandscapeView(
                    key='landscape_00',
                    description="System Landscape",
                )
            )
        return w.model