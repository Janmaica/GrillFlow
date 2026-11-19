import time
from concurrent.futures import ThreadPoolExecutor

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.screenmanager import NoTransition, ScreenManager, SlideTransition
from kivy.utils import platform

from consumption_store import ConsumptionStore
from expense_store import ExpenseStore
from firebase_auth import (
    INVALID_SESSION, AuthError, FirebaseAuth, Session, VerificationRequired, account_directory, clean_email,
    signup_fields,
)
from order_store import OrderStore
from product_store import ProductStore
from screens.add_product_screen import AddProductScreen
from screens.consumption_screen import ConsumptionScreen
from screens.dashboard_screen import DashboardScreen
from screens.expenses_screen import ExpensesScreen
from screens.login_screen import ForgotPasswordScreen, LoginScreen, SignupScreen, VerifyEmailScreen
from screens.new_order_screen import NewOrderScreen
from screens.order_history_screen import OrderHistoryScreen
from screens.payment_screen import PaymentScreen
from screens.products_screen import ProductsScreen
from screens.profile_screen import ProfileScreen
from screens.receipt_screen import ReceiptScreen
from screens.reports_screen import ReportsScreen
from screens.sales_screen import SalesScreen
from screens.splash_screen import SplashScreen
from screens.utang_screen import UtangScreen
from session_vault import SessionVault


CHECK_INTERVAL = 300
RESEND_INTERVAL = 60
AUTH_SCREENS = {"splash", "login", "signup", "forgot", "verify"}


class GrillFlowApp(App):
    def build(self):
        self.title = "GrillFlow"
        self.auth = self.create_auth()
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="firebase-auth")
        self.session = None
        self.challenge = None
        self.resend_at = 0
        self.next_check = 0
        self.operation = 0
        self.busy = False
        self.starting = True
        self.continuing = False
        self.startup_error = ""
        self.logout_blocked = False
        self.manager = ScreenManager()
        self.manager.add_widget(SplashScreen(name="splash"))
        for name, screen in (("login", LoginScreen), ("signup", SignupScreen),
                             ("forgot", ForgotPasswordScreen), ("verify", VerifyEmailScreen)):
            self.manager.add_widget(screen(self, name=name))
        return self.manager

    def create_auth(self):
        return FirebaseAuth.from_project_config(SessionVault(self.user_data_dir, platform), android=platform == "android")

    def on_start(self):
        self._task(self.auth.restore, self._startup_finished, self._startup_finished)
        self.session_check = Clock.schedule_interval(self._check_session, 5)

    def _startup_finished(self, result):
        self.starting = False
        if isinstance(result, AuthError):
            self.session = None
            self.startup_error = str(result)
        else:
            self.session = result
            if result:
                self._schedule_next_check()
        if self.continuing:
            self.continue_from_splash()

    def continue_from_splash(self):
        if self.starting:
            self.continuing = True
        elif self.session:
            if time.monotonic() >= self.next_check or (
                self.session.offline and not self.auth.offline_allowed(self.session)
            ):
                active = self.session
                self.starting = self.continuing = True
                self._task(lambda: self.auth.restore(active), self._resume_finished, self._startup_finished)
            else:
                self.continuing = False
                self._activate(self.session)
        else:
            self.continuing = False
            self.show("login", message=self.startup_error)
            self.startup_error = ""

    def _resume_finished(self, session):
        self.starting = self.continuing = False
        self._activate(session)

    def _task(self, work, success, failure=None):
        if self.busy:
            return
        self.busy = True
        self.operation += 1
        operation = self.operation
        screen = self.manager.current_screen
        if hasattr(screen, "set_busy"):
            screen.set_busy(True)
            screen.message("Please wait…")

        def finished(future):
            try:
                result = future.result()
                callback = success
            except AuthError as error:
                result, callback = error, failure
            except Exception:
                # Don't log worker exceptions, which could contain response or credential data.
                result, callback = AuthError("SERVICE"), failure

            def deliver(_):
                if self.operation != operation:
                    return
                self.busy = False
                if hasattr(screen, "set_busy"):
                    screen.set_busy(False)
                    screen.message("")
                if callback:
                    callback(result)
                elif hasattr(screen, "message"):
                    screen.message(str(result))

            Clock.schedule_once(deliver)

        self.worker.submit(work).add_done_callback(finished)

    def show(self, name, email=None, *, message=""):
        if self.busy or self.session or name not in AUTH_SCREENS:
            return
        self.challenge = None
        screen = self.manager.get_screen(name)
        if getattr(screen, "email", None) is not None and email is not None:
            screen.email.text = email
        if hasattr(screen, "message"):
            screen.message(message)
            screen.scroll.scroll_y = 1
        self.manager.current = name

    def login(self, email, password):
        if self.busy:
            return
        if self.logout_blocked:
            self.logout()
            return
        screen = self.manager.get_screen("login")
        try:
            email = clean_email(email)
            if not password:
                raise ValueError("Enter your password.")
        except ValueError as error:
            screen.message(str(error))
            return
        screen.clear_passwords()

        def work():
            tokens = self.auth.sign_in(email, password)
            profile = self.auth.lookup_profile(tokens)
            return self.auth.remember(tokens, profile) if profile.verified else tokens

        def complete(result):
            if isinstance(result, Session):
                self._activate(result)
            else:
                self._show_verification(result, email, "", str(AuthError("VERIFY")))

        self._task(work, complete)

    def signup(self, name, email, password, confirmation):
        if self.busy or self.logout_blocked:
            return
        screen = self.manager.get_screen("signup")
        try:
            name, email, password = signup_fields(name, email, password, confirmation)
        except ValueError as error:
            screen.message(str(error))
            return
        screen.clear_passwords()

        def work():
            tokens = self.auth.register(email, password)
            pending_name = name
            try:
                self.auth.update_name(tokens, name)
                pending_name = ""
                self.auth.send_verification(tokens)
                note = "We've sent a verification link to your email address. Please verify your email before continuing."
            except AuthError:
                note = "Your account was created. Use Resend Verification Email to try sending the link again."
            return tokens, pending_name, note

        def complete(result):
            tokens, pending_name, note = result
            self.resend_at = time.monotonic() + RESEND_INTERVAL
            self._show_verification(tokens, email, pending_name, note)

        self._task(work, complete)

    def _show_verification(self, tokens, email, name, message):
        self.show("verify", message=message)
        self.challenge = (tokens, name)
        self.manager.get_screen("verify").address.text = email

    def _verify(self, *, resend):
        if self.busy or not self.challenge:
            return
        screen = self.manager.get_screen("verify")
        if resend:
            remaining = self.resend_at - time.monotonic()
            if remaining > 0:
                screen.message(f"Wait {int(remaining) + 1} seconds before resending.")
                return
            self.resend_at = time.monotonic() + RESEND_INTERVAL
        tokens, name = self.challenge

        def work():
            fresh = self.auth.refresh(tokens.refresh_token)
            if fresh.uid != tokens.uid:
                raise AuthError("INVALID_ID_TOKEN")
            pending_name = name
            if name:
                self.auth.update_name(fresh, name)
                pending_name = ""
            profile = self.auth.lookup_profile(fresh)
            if profile.verified:
                return self.auth.remember(fresh, profile), None, ""
            if resend:
                self.auth.send_verification(fresh)
            return None, (fresh, pending_name), (
                "Verification email sent. Check your inbox and spam folder." if resend
                else "Your email is still unverified. Open the link and try again."
            )

        def complete(result):
            session, challenge, note = result
            self.challenge = challenge
            if session:
                self._activate(session)
            else:
                screen.message(note)

        self._task(work, complete)

    def check_verification(self):
        self._verify(resend=False)

    def resend_verification(self):
        self._verify(resend=True)

    def send_reset(self, email):
        if self.busy:
            return
        screen = self.manager.get_screen("forgot")
        try:
            email = clean_email(email)
        except ValueError as error:
            screen.message(str(error))
            return
        self._task(lambda: self.auth.reset_password(email), lambda _: screen.message(
            "If an account exists for this email, password reset instructions will be sent."
        ))

    def _activate(self, session):
        if self.manager.has_screen("dashboard"):
            return
        try:
            directory = account_directory(self.user_data_dir, self.auth.project, session.uid)
        except (OSError, AuthError):
            self.session = None
            self.show("login", message="Could not open this account's business data.")
            return
        self.session = session
        self.challenge = None
        self._schedule_next_check()
        store = ProductStore(directory)
        orders = OrderStore(store)
        expenses = ExpenseStore(store)
        consumption = ConsumptionStore(store)
        manager = self.manager
        manager.add_widget(DashboardScreen(orders, expenses, consumption, name="dashboard"))
        manager.add_widget(ProfileScreen(self, directory, name="profile"))
        manager.add_widget(ProductsScreen(store, name="products"))
        manager.add_widget(AddProductScreen(store, name="add_product"))
        manager.add_widget(SalesScreen(orders, name="sales"))
        manager.add_widget(NewOrderScreen(store, orders, name="new_order"))
        manager.add_widget(PaymentScreen(orders, name="payment"))
        manager.add_widget(ReceiptScreen(orders, name="receipt"))
        manager.add_widget(OrderHistoryScreen(orders, name="order_history"))
        manager.add_widget(UtangScreen(orders, name="utang"))
        manager.add_widget(ReportsScreen(orders, expenses, name="reports"))
        manager.add_widget(ExpensesScreen(expenses, name="expenses"))
        manager.add_widget(ConsumptionScreen(consumption, name="family_consumption"))
        manager.current = "dashboard"

    def _schedule_next_check(self):
        session = self.session
        delay = 30 if session.offline else max(0, min(CHECK_INTERVAL, session.expires_at - self.auth.now() - 60))
        self.next_check = time.monotonic() + delay

    def _check_session(self, *_):
        if not self.session or not self.manager.has_screen("dashboard"):
            return
        if self.session.offline and not self.auth.offline_allowed(self.session):
            self._end_session(str(AuthError("EXPIRED")))
            return
        if self.busy or time.monotonic() < self.next_check:
            return
        active = self.session

        self._task(lambda: self.auth.restore(active), self._session_updated, self._session_failure)

    def _session_updated(self, session):
        self.session = session
        self._schedule_next_check()
        if self.manager.has_screen("profile"):
            profile = self.manager.get_screen("profile")
            profile.render(session)
            if session.offline and self.manager.current == "profile":
                profile.message("Connect to the internet to update your name or change your password.")

    def _session_failure(self, error):
        self._end_session(str(error))
        if isinstance(error, VerificationRequired):
            self._show_verification(error.tokens, error.email, "", str(error))

    def refresh_profile(self):
        self.next_check = 0
        self._check_session()

    def _profile_action(self, action, message):
        if self.busy or not self.session or self.manager.current != "profile" or self.session.offline:
            return False
        current = self.session
        screen = self.manager.get_screen("profile")

        def complete(session):
            self._session_updated(session)
            screen.message(message)

        def failed(error):
            if error.code in INVALID_SESSION or error.code in {"VERIFY", "PROJECT_NUMBER_MISMATCH"}:
                self._session_failure(error)
            else:
                screen.message(str(error))
                if error.code == "NETWORK":
                    self.next_check = 0

        self._task(lambda: action(current), complete, failed)
        return True

    def update_profile_name(self, name):
        return self._profile_action(lambda session: self.auth.change_profile_name(session, name),
                                    "Profile updated successfully.")

    def send_profile_password_reset(self):
        return self._profile_action(self.auth.send_profile_password_reset,
                                    "A password reset link was sent to your account email.")

    def _end_session(self, message):
        self.operation += 1
        self.busy = False
        self.session = self.challenge = None
        manager = self.manager
        manager.transition.stop()
        manager.transition = NoTransition()
        self.show("login", "", message=message)
        for screen in manager.screens[:]:
            if screen.name not in AUTH_SCREENS:
                if screen.name == "profile":
                    screen.clear()
                manager.remove_widget(screen)
            elif hasattr(screen, "fields"):
                for field in screen.fields:
                    field.text = ""
                    field.reset_undo()
                if screen.name == "verify":
                    screen.address.text = ""
        manager.transition = SlideTransition()
        manager.get_screen("login").set_busy(False)

    def logout(self):
        self._end_session("")
        self.logout_blocked = True

        def cleared(_):
            self.logout_blocked = False
            self.manager.get_screen("login").message("You have been logged out.")

        self._task(self.auth.vault.clear, cleared, lambda _: self.manager.get_screen("login").message(
            "Could not remove the saved session. Press Log In to retry signing out."
        ))

    def on_pause(self):
        return True

    def on_resume(self):
        self.next_check = 0
        self._check_session()

    def on_stop(self):
        self.session_check.cancel()
        self.worker.shutdown(wait=False)


if __name__ == "__main__":
    if platform != "android":
        Window.size = (400, 750)
    Window.clearcolor = (23 / 255, 17 / 255, 14 / 255, 1)
    GrillFlowApp().run()
