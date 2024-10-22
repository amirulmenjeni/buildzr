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

        w = Workspace('w', scope='landscape')\
                .contains(
                    Person('Personal Banking Customer'),
                    Person('Customer Service Staff'),
                    Person('Back Office Staff'),
                    SoftwareSystem('ATM'),
                    SoftwareSystem('Internet Banking System'),
                    SoftwareSystem('Email System'),
                    SoftwareSystem('Mainframe Banking System'),
                )\
                .where(lambda w: [
                    w.person().personal_banking_customer >> "Withdraws cash using" >> w.software_system().atm,
                    w.person().personal_banking_customer >> "Views account balance, and makes payments using" >> w.software_system().internet_banking_system,
                    w.software_system().email_system >> "Sends e-mail to" >> w.person().personal_banking_customer,
                    w.software_system().personal_banking_customer >> "Ask questions to" >> w.person().customer_service_staff,
                    w.person().customer_service_staff >> "Uses" >> w.software_system().mainframe_banking_system,
                    w.person().back_office_staff >> "Uses" >> w.software_system().mainframe_banking_system,
                    w.software_system().atm >> "Uses" >> w.software_system().mainframe_banking_system,
                    w.software_system().internet_banking_system >> "Gets account information from, and makes payments using" >> w.software_system().mainframe_banking_system,
                    w.software_system().internet_banking_system >> "Sends e-mail using" >> w.software_system().email_system,
                ])\
                .with_views(
                    SystemLandscapeView(
                        key='landscape_00',
                        description="System Landscape",
                    )
                )\
                .get_workspace()

        return w.model