from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import json
from datetime import datetime, timedelta

@register("account_book", "YourName", "一个简单的记账本插件", "1.0.0")
class AccountBookPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_file = "data/account_book_data.json"
        self._load_data()

    def _load_data(self):
        """加载记账数据"""
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        except FileNotFoundError:
            self.data = []

    def _save_data(self):
        """保存记账数据"""
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=4)

    @filter.command("+")
    async def add_income(self, event: AstrMessageEvent, 类目: str, 金额: float, 日期: str = None):
        """添加收入记录
        
        Args:
            类目 (str): 收入类目
            金额 (float): 收入金额
            日期 (str, optional): 收入日期，格式为YYYY-MM-DD，默认为当前日期
        """
        if not 日期:
            日期 = datetime.now().strftime("%Y-%m-%d")
        
        try:
            datetime.strptime(日期, "%Y-%m-%d")
        except ValueError:
            return event.plain_result("日期格式错误，请使用YYYY-MM-DD格式")
        
        self.data.append({"date": 日期, "category": 类目, "amount": 金额})
        self._save_data()
        
        return event.plain_result(f"✅成功添加收入：{类目} {金额}元 ({日期})")

    @filter.command_group("查询收入")
    def query_income_group(self):
        """查询收入指令组"""
        pass

    @query_income_group.command("t")
    async def query_income_by_day(self, event: AstrMessageEvent, 日期: str):
        """按天查询收入
        
        Args:
            日期 (str): 日期，格式为YYYY-MM-DD
        """
        try:
            target_date = datetime.strptime(日期, "%Y-%m-%d")
        except ValueError:
            return event.plain_result("日期格式错误，请使用YYYY-MM-DD格式")
        
        total_income = 0
        income_list = []
        
        for record in self.data:
            record_date = datetime.strptime(record["date"], "%Y-%m-%d")
            if record_date == target_date:
                total_income += record["amount"]
                income_list.append(f"• {record['category']}: {record['amount']}元")
        
        if income_list:
            result = f"📅{日期}收入总计: {total_income}元\n" + "\n".join(income_list)
        else:
            result = f"📅{日期}没有收入记录"
            
        return event.plain_result(result)

    @query_income_group.command("z")
    async def query_income_by_week(self, event: AstrMessageEvent, 起始日期: str):
        """按周查询收入
        
        Args:
            起始日期 (str): 本周起始日期，格式为YYYY-MM-DD
        """
        try:
            start = datetime.strptime(起始日期, "%Y-%m-%d")
            end = start + timedelta(days=6)
        except ValueError:
            return event.plain_result("日期格式错误，请使用YYYY-MM-DD格式")
        
        total_income = 0
        income_list = []
        
        for record in self.data:
            record_date = datetime.strptime(record["date"], "%Y-%m-%d")
            if start <= record_date <= end:
                total_income += record["amount"]
                income_list.append(f"• {record['date']} {record['category']}: {record['amount']}元")
        
        if income_list:
            result = f"📅{起始日期}~{end.strftime('%Y-%m-%d')}收入总计: {total_income}元\n" + "\n".join(income_list)
        else:
            result = f"📅{起始日期}~{end.strftime('%Y-%m-%d')}没有收入记录"
            
        return event.plain_result(result)

    @query_income_group.command("y")
    async def query_income_by_month(self, event: AstrMessageEvent, 月份: str):
        """按月查询收入
        
        Args:
            月份 (str): 月份，格式为YYYY-MM
        """
        try:
            target_month = datetime.strptime(月份, "%Y-%m")
            start = target_month.replace(day=1)
            
            if target_month.month == 12:
                end = target_month.replace(year=target_month.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                end = target_month.replace(month=target_month.month + 1, day=1) - timedelta(days=1)
                
        except ValueError:
            return event.plain_result("日期格式错误，请使用YYYY-MM格式")
        
        total_income = 0
        income_list = []
        
        for record in self.data:
            record_date = datetime.strptime(record["date"], "%Y-%m-%d")
            if start <= record_date <= end:
                total_income += record["amount"]
                income_list.append(f"• {record['date']} {record['category']}: {record['amount']}元")
        
        if income_list:
            result = f"📅{月份}收入总计: {total_income}元\n" + "\n".join(income_list)
        else:
            result = f"📅{月份}没有收入记录"
            
        return event.plain_result(result)

    @query_income_group.command("++")
    async def query_income_by_year(self, event: AstrMessageEvent, 年份: str):
        """按年查询收入
        
        Args:
            年份 (str): 年份，格式为YYYY
        """
        try:
            target_year = datetime.strptime(年份, "%Y")
            start = target_year.replace(month=1, day=1)
            end = target_year.replace(year=target_year.year + 1, month=1, day=1) - timedelta(days=1)
        except ValueError:
            return event.plain_result("日期格式错误，请使用YYYY格式")
        
        total_income = 0
        income_list = []
        
        for record in self.data:
            record_date = datetime.strptime(record["date"], "%Y-%m-%d")
            if start <= record_date <= end:
                total_income += record["amount"]
                income_list.append(f"• {record['date'][:7]} {record['category']}: {record['amount']}元")
        
        if income_list:
            result = f"📅{年份}收入总计: {total_income}元\n" + "\n".join(income_list)
        else:
            result = f"📅{年份}没有收入记录"
            
        return event.plain_result(result)

    @filter.command("ls")
    async def list_categories(self, event: AstrMessageEvent):
        """列出所有收入类目"""
        categories = {}
        for record in self.data:
            cat = record["category"]
            categories[cat] = categories.get(cat, 0) + record["amount"]
        
        if categories:
            cat_list = [f"• {cat}: {amount}元" for cat, amount in categories.items()]
            return event.plain_result(f"📊收入类目统计:\n" + "\n".join(cat_list))
        else:
            return event.plain_result("📊暂无收入记录")

    @filter.command("lst")
    async def total_income(self, event: AstrMessageEvent):
        """计算总收入"""
        if not self.data:
            return event.plain_result("📊暂无收入记录")
        
        total = sum(record["amount"] for record in self.data)
        return event.plain_result(f"📊总收入: {total}元")

    @filter.command("help")
    async def show_help(self, event: AstrMessageEvent):
        """显示帮助信息"""
        help_text = """💰记账本插件帮助:
/+ 类目 金额 [日期] - 添加收入记录(日期格式:YYYY-MM-DD)
/t 日期 - 按天查询收入
/z 起始日期 - 按周查询收入
/y 月份 - 按月查询收入
/++ 年份 - 按年查询收入
/ls - 查看所有收入类目及统计
/lst - 查看总收入
/help - 显示帮助信息

📌示例:
/+ 工资 5000 2025-05-15
/t 2025-05-15
/z 2025-05-11
/y 2025-05
/++ 2025
/ls
/lst
"""
        return event.plain_result(help_text)