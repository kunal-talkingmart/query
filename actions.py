
# This files contains your custom actions which can be used to run
# custom Python code.
#
# See this guide on how to implement these action:
# https://rasa.com/docs/rasa/core/actions/#custom-actions/


# This is a simple example for a custom action which utters "Hello World!"

# from typing import Any, Text, Dict, List
#
# from rasa_sdk import Action, Tracker
# from rasa_sdk.executor import CollectingDispatcher
#
#
# class ActionHelloWorld(Action):
#
#     def name(self) -> Text:
#         return "action_hello_world"
#
#     def run(self, dispatcher: CollectingDispatcher,
#             tracker: Tracker,
#             domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
#
#         dispatcher.utter_message(text="Hello World!")
#
#         return []

import os
import sys
sys.path.append(os.path.dirname(os.path.realpath(__file__)))
from rasa_sdk import Action
import query

from typing import Dict, Text, Any, List, Union, Optional
import logging
from rasa_sdk import Tracker, Action
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.forms import FormAction, REQUESTED_SLOT
from rasa_sdk.events import (
    SlotSet,
    EventType,
    ActionExecuted,
    SessionStarted,
    Restarted,
    FollowupAction,
)
#from actions.parsing import (
#    parse_duckling_time_as_interval,
#    parse_duckling_time,
#    get_entity_details,
#    parse_duckling_currency,
#)
#from actions.profile import create_mock_profile
#from dateutil import parser

import pyodbc

logger = logging.getLogger(__name__)


def custom_request_next_slot(
    form,
    dispatcher: "CollectingDispatcher",
    tracker: "Tracker",
    domain: Dict[Text, Any],
) -> Optional[List[EventType]]:
    """Request the next slot and utter template if needed,
        else return None"""

    for slot in form.required_slots(tracker):
        if form._should_request_slot(tracker, slot):
            logger.debug(f"Request next slot '{slot}'")
            dispatcher.utter_message(
                template=f"utter_ask_{form.name()}_{slot}", **tracker.slots
            )
            return [SlotSet(REQUESTED_SLOT, slot)]

    return None


class PayCCForm(FormAction):
    """Pay credit card form..."""

    def name(self) -> Text:
        """Unique identifier of the form"""

        return "cc_payment_form"

    def request_next_slot(
        self,
        dispatcher: "CollectingDispatcher",
        tracker: "Tracker",
        domain: Dict[Text, Any],
    ) -> Optional[List[EventType]]:

        return custom_request_next_slot(self, dispatcher, tracker, domain)

    @staticmethod
    def required_slots(tracker: Tracker) -> List[Text]:
        """A list of required slots that the form has to fill"""

        return ["credit_card", "payment_amount", "time", "confirm"]

    def slot_mappings(self) -> Dict[Text, Union[Dict, List[Dict]]]:
        """A dictionary to map required slots to
            - an extracted entity
            - intent: value pairs
            - a whole message
            or a list of them, where a first match will be picked"""

        return {
            "payment_amount": [
                self.from_entity(entity="payment_amount"),
                self.from_entity(entity="amount-of-money"),
                self.from_entity(entity="number"),
            ],
            "confirm": [
                self.from_intent(value=True, intent="affirm"),
                self.from_intent(value=False, intent="deny"),
            ],
        }

    def validate_payment_amount(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        """Validate payment amount value."""

        credit_card = tracker.get_slot("credit_card")
        cc_balance = tracker.get_slot("credit_card_balance")
        account_balance = float(tracker.get_slot("account_balance"))
        try:
            entity = get_entity_details(
                tracker, "amount-of-money"
            ) or get_entity_details(tracker, "number")
            amount_currency = parse_duckling_currency(entity)
            if not amount_currency:
                raise (TypeError)
            if account_balance < float(amount_currency.get("amount_of_money")):
                dispatcher.utter_message(template="utter_insufficient_funds")
                return {"payment_amount": None}
            return amount_currency
        except (TypeError, AttributeError):
            pass
        if value and value.lower() in cc_balance.get(credit_card.lower()):
            key = value.lower()
            amount = cc_balance.get(credit_card.lower()).get(key)
            amount_type = f" (your {key})"

            if account_balance < float(amount):
                dispatcher.utter_message(template="utter_insufficient_funds")
                return {"payment_amount": None}
            return {
                "payment_amount": f"{amount:.2f}",
                "payment_amount_type": amount_type,
                "currency": "$",
            }

        else:
            dispatcher.utter_message(template="utter_no_payment_amount")
            return {"payment_amount": None}

    def validate_credit_card(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        """Validate credit_card value."""

        cc_balance = tracker.get_slot("credit_card_balance")
        if value and value.lower() in list(cc_balance.keys()):
            return {"credit_card": value.title()}
        else:
            dispatcher.utter_message(template="utter_no_creditcard")
            return {"credit_card": None}

    def validate_time(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        """Validate time value."""

        timeentity = get_entity_details(tracker, "time")
        parsedtime = parse_duckling_time(timeentity)
        if not parsedtime:
            dispatcher.utter_message(template="utter_no_transactdate")
            return {"time": None}
        return parsedtime

    def submit(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict]:
        """Define what the form has to do
            after all required slots are filled"""

        account_balance = float(tracker.get_slot("account_balance"))
        credit_card = tracker.get_slot("credit_card")
        cc_balance = tracker.get_slot("credit_card_balance")
        payment_amount = float(tracker.get_slot("payment_amount"))
        amount_transferred = float(tracker.get_slot("amount_transferred"))

        if tracker.get_slot("confirm"):
            cc_balance[credit_card.lower()][
                "current balance"
            ] -= payment_amount
            account_balance = account_balance - payment_amount
            dispatcher.utter_message(template="utter_cc_pay_scheduled")

            return [
                SlotSet("credit_card", None),
                SlotSet("payment_amount", None),
                SlotSet("confirm", None),
                SlotSet("time", None),
                SlotSet("time_formatted", None),
                SlotSet("start_time", None),
                SlotSet("end_time", None),
                SlotSet("start_time_formatted", None),
                SlotSet("end_time_formatted", None),
                SlotSet("grain", None),
                SlotSet("amount_of_money", None),
                SlotSet(
                    "amount_transferred", amount_transferred + payment_amount,
                ),
                SlotSet("account_balance", f"{account_balance:.2f}"),
                SlotSet("credit_card_balance", cc_balance),
            ]
        else:
            dispatcher.utter_message(template="utter_cc_pay_cancelled")

        return [
            SlotSet("credit_card", None),
            SlotSet("payment_amount", None),
            SlotSet("confirm", None),
            SlotSet("time", None),
            SlotSet("time_formatted", None),
            SlotSet("start_time", None),
            SlotSet("end_time", None),
            SlotSet("start_time_formatted", None),
            SlotSet("end_time_formatted", None),
            SlotSet("grain", None),
        ]


class TransactSearchForm(FormAction):
    """Transaction search form"""

    def name(self) -> Text:
        """Unique identifier of the form"""

        return "transact_search_form"

    def request_next_slot(
        self,
        dispatcher: "CollectingDispatcher",
        tracker: "Tracker",
        domain: Dict[Text, Any],
    ) -> Optional[List[EventType]]:

        return custom_request_next_slot(self, dispatcher, tracker, domain)

    @staticmethod
    def required_slots(tracker: Tracker) -> List[Text]:
        """A list of required slots that the form has to fill"""

        return ["search_type", "time"]

    def slot_mappings(self) -> Dict[Text, Union[Dict, List[Dict]]]:
        """A dictionary to map required slots to
            - an extracted entity
            - intent: value pairs
            - a whole message
            or a list of them, where a first match will be picked"""

        return {
            "search_type": [
                self.from_trigger_intent(
                    intent="search_transactions", value="spend"
                ),
                self.from_trigger_intent(
                    intent="check_earnings", value="deposit"
                ),
            ],
        }

    def validate_vendor_name(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        """Validate vendor_name value."""

        if value and value.lower() in tracker.get_slot("vendor_list"):
            return {"vendor_name": value}
        else:
            dispatcher.utter_message(template="utter_no_vendor_name")
            return {"vendor_name": None}

    def validate_time(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        """Validate time value."""
        timeentity = get_entity_details(tracker, "time")
        parsedinterval = parse_duckling_time_as_interval(timeentity)
        if not parsedinterval:
            dispatcher.utter_message(template="utter_no_transactdate")
            return {"time": None}

        return parsedinterval

    def submit(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict]:
        """Define what the form has to do
            after all required slots are filled"""

        search_type = tracker.get_slot("search_type")
        transaction_history = tracker.get_slot("transaction_history")
        transactions_subset = transaction_history.get(search_type, {})
        vendor = tracker.get_slot("vendor_name")

        if vendor:
            transactions = transactions_subset.get(vendor.lower())
            vendor = f" with {vendor}"
        else:
            transactions = [
                v for k in list(transactions_subset.values()) for v in k
            ]
            vendor = ""

        start_time = parser.isoparse(tracker.get_slot("start_time"))
        end_time = parser.isoparse(tracker.get_slot("end_time"))

        for i in range(len(transactions) - 1, -1, -1):
            transaction = transactions[i]
            transaction_date = parser.isoparse(transaction.get("date"))

            if transaction_date < start_time or transaction_date > end_time:
                transactions.pop(i)

        numtransacts = len(transactions)
        total = sum([t.get("amount") for t in transactions])
        slotvars = {
            "total": f"{total:.2f}",
            "numtransacts": numtransacts,
            "start_time_formatted": tracker.get_slot("start_time_formatted"),
            "end_time_formatted": tracker.get_slot("end_time_formatted"),
            "vendor_name": vendor,
        }

        dispatcher.utter_message(
            template=f"utter_searching_{search_type}_transactions", **slotvars
        )
        dispatcher.utter_message(
            template=f"utter_found_{search_type}_transactions", **slotvars
        )

        return [
            SlotSet("time", None),
            SlotSet("time_formatted", None),
            SlotSet("start_time", None),
            SlotSet("end_time", None),
            SlotSet("start_time_formatted", None),
            SlotSet("end_time_formatted", None),
            SlotSet("grain", None),
            SlotSet("search_type", None),
            SlotSet("vendor_name", None),
        ]


class TransferForm(FormAction):
    """Transfer money form..."""

    def name(self) -> Text:
        """Unique identifier of the form"""

        return "transfer_form"

    def request_next_slot(
        self,
        dispatcher: "CollectingDispatcher",
        tracker: "Tracker",
        domain: Dict[Text, Any],
    ) -> Optional[List[EventType]]:

        return custom_request_next_slot(self, dispatcher, tracker, domain)

    @staticmethod
    def required_slots(tracker: Tracker) -> List[Text]:
        """A list of required slots that the form has to fill"""

        return ["PERSON", "amount_of_money", "confirm"]

    def slot_mappings(self) -> Dict[Text, Union[Dict, List[Dict]]]:
        """A dictionary to map required slots to
            - an extracted entity
            - intent: value pairs
            - a whole message
            or a list of them, where a first match will be picked"""

        return {
            "amount_of_money": [
                self.from_entity(entity="amount-of-money"),
                self.from_entity(entity="number"),
            ],
            "confirm": [
                self.from_intent(value=True, intent="affirm"),
                self.from_intent(value=False, intent="deny"),
            ],
        }

    def validate_PERSON(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        name = value.title() if value else None
        known_recipients = tracker.get_slot("known_recipients")
        first_names = [name.split()[0] for name in known_recipients]
        if name in known_recipients:
            return {"PERSON": name}
        elif name in first_names:
            index = first_names.index(name)
            fullname = known_recipients[index]
            return {"PERSON": fullname}
        else:
            dispatcher.utter_message(template="utter_unknown_recipient")
            return {"PERSON": None}

    def validate_amount_of_money(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:

        account_balance = float(tracker.get_slot("account_balance"))
        try:
            entity = get_entity_details(
                tracker, "amount-of-money"
            ) or get_entity_details(tracker, "number")
            amount_currency = parse_duckling_currency(entity)
            if not amount_currency:
                raise (TypeError)
            if account_balance < float(amount_currency.get("amount_of_money")):
                dispatcher.utter_message(template="utter_insufficient_funds")
                return {"amount_of_money": None}
            return amount_currency
        except (TypeError, AttributeError):
            dispatcher.utter_message(template="utter_no_payment_amount")
            return {"amount_of_money": None}

    def submit(self, dispatcher, tracker, domain):
        if tracker.get_slot("confirm"):
            amount_of_money = float(tracker.get_slot("amount_of_money"))
            account_balance = float(tracker.get_slot("account_balance"))

            updated_account_balance = account_balance - amount_of_money

            dispatcher.utter_message(template="utter_transfer_complete")

            amount_transferred = tracker.get_slot("amount_transferred")
            return [
                SlotSet("PERSON", None),
                SlotSet("amount_of_money", None),
                SlotSet("confirm", None),
                SlotSet(
                    "amount_transferred", amount_transferred + amount_of_money
                ),
                SlotSet("account_balance", f"{updated_account_balance:.2f}"),
            ]
        else:
            dispatcher.utter_message(template="utter_transfer_cancelled")
            return [
                SlotSet("PERSON", None),
                SlotSet("amount_of_money", None),
                SlotSet("confirm", None),
            ]


class ActionAccountBalance(Action):
    def name(self):
        return "action_account_balance"

    def run(self, dispatcher, tracker, domain):
        account_balance = float(tracker.get_slot("account_balance"))
        amount = tracker.get_slot("amount_transferred")
        if amount:
            amount = float(tracker.get_slot("amount_transferred"))
            init_account_balance = account_balance + amount
            dispatcher.utter_message(
                template="utter_changed_account_balance",
                init_account_balance=f"{init_account_balance:.2f}",
                account_balance=f"{account_balance:.2f}",
            )
            return [SlotSet("payment_amount", None)]
        else:
            dispatcher.utter_message(
                template="utter_account_balance",
                init_account_balance=f"{account_balance:.2f}",
            )
            return [SlotSet("payment_amount", None)]


class ActionCreditCardBalance(Action):
    def name(self):
        return "action_credit_card_balance"

    def run(self, dispatcher, tracker, domain):
        credit_card_balance = tracker.get_slot("credit_card_balance")
        credit_card = tracker.get_slot("credit_card")

        if credit_card and credit_card.lower() in credit_card_balance:
            current_balance = credit_card_balance[credit_card.lower()][
                "current balance"
            ]
            dispatcher.utter_message(
                template="utter_credit_card_balance",
                credit_card=credit_card.title(),
                amount_of_money=f"{current_balance:.2f}",
            )
            return [SlotSet("credit_card", None)]
        else:
            for credit_card in credit_card_balance.keys():
                current_balance = credit_card_balance[credit_card][
                    "current balance"
                ]
                dispatcher.utter_message(
                    template="utter_credit_card_balance",
                    credit_card=credit_card.title(),
                    amount_of_money=f"{current_balance:.2f}",
                )

            return []


class ActionRecipients(Action):
    def name(self):
        return "action_recipients"

    def run(self, dispatcher, tracker, domain):
        recipients = tracker.get_slot("known_recipients")
        formatted_recipients = "\n" + "\n".join(
            [f"- {recipient}" for recipient in recipients]
        )
        dispatcher.utter_message(
            template="utter_recipients",
            formatted_recipients=formatted_recipients,
        )
        return []


class ActionSessionStart(Action):
    def name(self) -> Text:
        return "action_session_start"

    @staticmethod
    def _slot_set_events_from_tracker(tracker: "Tracker",) -> List["SlotSet"]:
        """Fetch SlotSet events from tracker and carry over keys and values"""

        return [
            SlotSet(key=event.get("name"), value=event.get("value"),)
            for event in tracker.events
            if event.get("event") == "slot"
        ]

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[EventType]:

        # the session should begin with a `session_started` event
        events = [SessionStarted()]

        events.extend(self._slot_set_events_from_tracker(tracker))

        # create mock profile
        # user_profile = create_mock_profile()

        # initialize slots from mock profile
        #for key, value in user_profile.items():
        #    if value is not None:
        #        events.append(SlotSet(key=key, value=value))

        # an `action_listen` should be added at the end
        events.append(ActionExecuted("action_listen"))

        return events


class ActionRestart(Action):
    def name(self) -> Text:
        return "action_restart"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[EventType]:

        return [Restarted(), FollowupAction("action_session_start")]

class ActionChitchat(Action):
    """Returns the chitchat utterance dependent on the intent"""

    def name(self) -> Text:
        """Unique identifier of the action"""

        return "action_chitchat"

    def run(self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List:

        intent = tracker.latest_message['intent'].get('name')

        # retrieve the correct chitchat utterance dependent on the intent
        if intent in ['ask_builder', 'ask_weather', 'ask_howdoing',
                      'ask_howold', 'ask_languagesbot', 'ask_restaurant',
                      'ask_time', 'ask_wherefrom', 'ask_whoami',
                      'handleinsult', 'telljoke', 'ask_whatismyname']:
            dispatcher.utter_template('utter_' + intent, tracker)

        return []


class SearchCategory(Action):
    """Returns list of categories"""

    def name(self) -> Text:
        """Unique identifier of the action"""

        return "action_search_category"

    def run(self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List:

            #cnxn = pyodbc.connect('DRIVER={ODBC Driver 17 for SQL Server};SERVER=192.168.1.16;DATABASE=talkingmart;UID=sa;PWD=rasa123!')
            #cursor = cnxn.cursor()

            #TODO: Absolutely ghastly code below; but need to whip up a demo tomorrow at 9, and it's 5 pm already
            #cursor.execute("SELECT top 3 category1 from categories group by category1") 
            msg = "Which of the following would you be interested in: "
            #records = cursor.fetchall()
            categories = ["watch", "Smartphone", "furniture", "Organic-product"]

            numcategories = len(categories)
            countcategories = 0
            for cat in categories:
                msg = msg + cat
                countcategories = countcategories + 1
                if numcategories == countcategories + 1:
                    msg = msg + " or "
                else:
                    msg = msg + ", "
            #TODO: adding an extra comma here; fix that

            msg = msg + "?"
            dispatcher.utter_message(msg)
            return []

class SearchSubCategory(Action):
    """Returns list of categories"""

    def name(self) -> Text:
        """Unique identifier of the action"""

        return "action_search_subcategory"

    def run(self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List:

            #cnxn = pyodbc.connect('DRIVER={ODBC Driver 17 for SQL Server};SERVER=192.168.1.16;DATABASE=talkingmart;UID=sa;PWD=rasa123!')
            #cursor = cnxn.cursor()

            category = tracker.get_slot("category")
            print(category)
            #qry = "SELECT top 3 category3 from categories where category1 like '%" + category + "%' order by newid()"
            #print (qry)
            #TODO: Absolutely ghastly code below; but need to whip up a demo tomorrow at 9, and it's 5 pm already
            #cursor.execute(qry) 
            msg = "Many great choices here.  How about any of the following: "
            #records = cursor.fetchall()
            #records = "first-product"
            #numcategories = len(records)
            #countcategories = 0
            #for row in records:
                #msg = msg + row.category3 
                #countcategories = countcategories + 1
               #if numcategories == countcategories + 1:
 
                   #msg = msg + " or "
                #else:
                    #msg = msg + ", "
            #TODO: adding an extra comma here; fix that
            ProductList = query.productSearchByTag("watch");          
            productAll = ProductList['data']['products']['edges'];
            print("Here are all the products:")
            productHandleList = []
            for product in productAll:
                    # print (product['node']['handle'])
                productHandleList.append(product['node']['handle']);
            for producthandle in productHandleList:
                #print(producthandle);
                msg = msg + " " + producthandle

            dispatcher.utter_message(msg)
            return []


class SearchProduct(Action):
    """Returns list of products"""

    def name(self) -> Text:
        """Unique identifier of the action"""

        return "action_search_products"

    def run(self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List:

            cnxn = pyodbc.connect('DRIVER={ODBC Driver 17 for SQL Server};SERVER=192.168.1.16;DATABASE=talkingmart;UID=sa;PWD=rasa123!')
            cursor = cnxn.cursor()
            subcategory = tracker.get_slot("subcategory")

            #TODO: Still bbsolutely ghastly code below; but need to whip up a demo tomorrow at 9, and it's 5 pm already
            qry = "SELECT top 3 product, price from products where category3 like '%" + subcategory + "%' order by newid()"
            print (qry)
            #TODO: Absolutely ghastly code below; but need to whip up a demo tomorrow at 9, and it's 5 pm already
            cursor.execute(qry) 
            msg = "How about any of the following: "
            records = cursor.fetchall()
            numcategories = len(records)
            countcategories = 0
            for row in records:
                msg = msg + row.product + " for " +  str(round(row.price))
                countcategories = countcategories + 1
                if numcategories == countcategories + 1:
                    msg = msg + " or "
                else:
                    msg = msg + ", "
            #TODO: adding an extra comma here; fix that

            msg = msg + "?"
            dispatcher.utter_message(msg)
            return []


class AddToCart(Action):
    """Adds a product to cart"""

    def name(self) -> Text:
        """Unique identifier of the action"""

        return "action_addtocart"

    def run(self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List:

            cnxn = pyodbc.connect('DRIVER={ODBC Driver 17 for SQL Server};SERVER=192.168.1.16;DATABASE=talkingmart;UID=sa;PWD=rasa123!')
            cursor = cnxn.cursor()
            product = tracker.get_slot("product")

            #TODO: Still absolutely ghastly code below; but need to whip up a demo tomorrow at 9, and it's 5 pm already
            selectqry = "select * from cartitems where product like '%" + product + "%'"
            cursor.execute(selectqry) 
            partrecords = cursor.fetchall()
            numparts = len(partrecords)

            if numparts > 0:
                msg = "Product " + product + " is already in your cart"
            else:
                insertqry = "insert into cartitems select top 1 location, vendor, product, currency, price, 1 from products where product like '%" + product + "%'"
                print (insertqry)
                #TODO: Absolutely ghastly code below; but need to whip up a demo tomorrow at 9, and it's 5 pm already
                cursor.execute(insertqry) 
                cnxn.commit()
                msg = "Product " + product + " successfully added your cart"
                
            dispatcher.utter_message(msg)        
            return []


class ShowCart(Action):
    """Shows the current cart"""

    def name(self) -> Text:
        """Unique identifier of the action"""

        return "action_showcart"

    def run(self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List:

            cnxn = pyodbc.connect('DRIVER={ODBC Driver 17 for SQL Server};SERVER=192.168.1.16;DATABASE=talkingmart;UID=sa;PWD=rasa123!')
            cursor = cnxn.cursor()
            
            #TODO: Still absolutely ghastly code below; but need to whip up a demo tomorrow at 9, and it's 5 pm already
            selectqry = "select product from cartitems"
            cursor.execute(selectqry) 
            cartrecords = cursor.fetchall()
            numparts = len(cartrecords)
            if numparts == 0:
                dispatcher.utter_message("Your cart is empty.  Why don't you add something to it?  You'll both feel better!")
            else:
                for row in cartrecords:
                    dispatcher.utter_message(row.product)
                dispatcher.utter_message("Great set of items!  Would you like to checkout now?")        
            return []

