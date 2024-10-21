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
                    SoftwareSystem('E-mail System'),
                    SoftwareSystem('Mainframe Banking System'),
                )\
                .where(
                    lambda \
                        personal_banking_customer,
                        customer_service_staff,
                        back_office_staff,
                        atm,
                        internet_banking_system,
                        email_system,
                        mainframe_banking_system: [

                    personal_banking_customer >> "Withdraws cash using" >> atm,
                    personal_banking_customer >> "Views account balance, and makes payments using" >> internet_banking_system,
                    email_system >> "Sends e-mail to" >> personal_banking_customer,
                    personal_banking_customer >> "Ask questions to" >> customer_service_staff,
                    customer_service_staff >> "Uses" >> mainframe_banking_system,
                    back_office_staff >> "Uses" >> mainframe_banking_system,
                    atm >> "Uses" >> mainframe_banking_system,
                    internet_banking_system >> "Gets account information from, and makes payments using" >> mainframe_banking_system,
                    internet_banking_system >> "Sends e-mail using" >> email_system,
                ])\
                .with_views(
                    SystemLandscapeView(
                        key='landscape_00',
                        description="System Landscape",
                    )
                )\
                .get_workspace()

        return w.model