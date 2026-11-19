from kivy.app import App
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager
from kivy.utils import platform

from consumption_store import ConsumptionStore
from expense_store import ExpenseStore
from order_store import OrderStore
from product_store import ProductStore
from screens.add_product_screen import AddProductScreen
from screens.consumption_screen import ConsumptionScreen
from screens.dashboard_screen import DashboardScreen
from screens.expenses_screen import ExpensesScreen
from screens.login_screen import LoginScreen
from screens.new_order_screen import NewOrderScreen
from screens.order_history_screen import OrderHistoryScreen
from screens.payment_screen import PaymentScreen
from screens.products_screen import ProductsScreen
from screens.receipt_screen import ReceiptScreen
from screens.reports_screen import ReportsScreen
from screens.sales_screen import SalesScreen
from screens.splash_screen import SplashScreen
from screens.utang_screen import UtangScreen


class GrillFlowApp(App):
    def build(self):
        self.title = "GrillFlow"
        store = ProductStore(self.user_data_dir)
        orders = OrderStore(store)
        expenses = ExpenseStore(store)
        consumption = ConsumptionStore(store)
        manager = ScreenManager()
        manager.add_widget(SplashScreen(name="splash"))
        manager.add_widget(LoginScreen(name="login"))
        manager.add_widget(DashboardScreen(orders, expenses, consumption, name="dashboard"))
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
        return manager


if __name__ == "__main__":
    if platform != "android":
        Window.size = (400, 750)
    Window.clearcolor = (23 / 255, 17 / 255, 14 / 255, 1)
    GrillFlowApp().run()
