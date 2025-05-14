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
    async def add_income(self, event: AstrMessageEvent, *args):
        """添加收入记录
        
        用法:
            /+ 类目 金额          # 自动记录当前日期
            /+ 类目 金额 日期    # 指定日期(格式:YYYY-MM-DD)
        """
        # 验证参数数量
        if len(args) < 2:
            return MessageEventResult(plain_text="❌错误：请提供类目和金额！\n示例：/+ 工资 5000")
        
        类目 = args[0]
        金额 = args[1]
        
        # 验证金额是否为有效数字
        try:
            金额 = float(金额)
            if 金额 <= 0:
                raise ValueError("金额必须大于0")
        except ValueError as e:
            return MessageEventResult(plain_text=f"❌错误：金额必须是大于0的数字！({e})")
        
        # 处理可选的日期参数
        if len(args) >= 3:
            日期 = args[2]
            try:
                datetime.strptime(日期, "%Y-%m-%d")
            except ValueError:
                return MessageEventResult(plain_text="❌日期格式错误，请使用YYYY-MM-DD格式")
        else:
            # 没有提供日期时，自动记录当前日期
            日期 = datetime.now().strftime("%Y-%m-%d")
        
        self.data.append({"date": 日期, "category": 类目, "amount": 金额})
        self._save_data()
        
        return MessageEventResult(plain_text=f"✅成功添加收入：{类目} {金额}元 ({日期})")

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
            return MessageEventResult(plain_text="❌日期格式错误，请使用YYYY-MM-DD格式")
        
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
            
        return MessageEventResult(plain_text=result)

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
            return MessageEventResult(plain_text="❌日期格式错误，请使用YYYY-MM-DD格式")
        
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
            
        return MessageEventResult(plain_text=result)

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
            return MessageEventResult(plain_text="❌日期格式错误，请使用YYYY-MM格式")
        
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
            
        return MessageEventResult(plain_text=result)

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
            return MessageEventResult(plain_text="❌日期格式错误，请使用YYYY格式")
        
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
            
        return MessageEventResult(plain_text=result)

    @filter.command("ls")
    async def list_categories(self, event: AstrMessageEvent):
        """列出所有收入类目及详细统计"""
        if not self.data:
            return MessageEventResult(plain_text="📊暂无收入记录")
        
        # 按类目统计总收入
        categories = {}
        for record in self.data:
            cat = record["category"]
            categories[cat] = categories.get(cat, 0) + record["amount"]
        
        # 计算总收入
        total = sum(categories.values())
        
        # 按金额排序
        sorted_cats = sorted(categories.items(), key=lambda x: x[1], reverse=True)
        
        # 生成图表
        chart = "📊收入类目分布\n"
        for cat, amount in sorted_cats:
            percent = amount / total * 100
            # 生成简单的文本柱状图
            bar = "█" * int(percent / 5)
            chart += f"• {cat}: {amount}元 ({percent:.1f}%) {bar}\n"
        
        chart += f"\n💰总收入: {total}元"
        
        return MessageEventResult(plain_text=chart)

    @filter.command("lsd")
    async def list_categories_detail(self, event: AstrMessageEvent):
        """按类目详细统计收入"""
        if not self.data:
            return MessageEventResult(plain_text="📊暂无收入记录")
        
        # 按类目分组
        category_data = {}
        for record in self.data:
            cat = record["category"]
            if cat not in category_data:
                category_data[cat] = []
            category_data[cat].append(record)
        
        # 生成详细统计
        result = "📊收入类目详细统计\n"
        for cat, records in category_data.items():
            cat_total = sum(r["amount"] for r in records)
            result += f"\n🔸{cat} ({len(records)}笔，总计: {cat_total}元):\n"
            
            # 按日期排序
            sorted_records = sorted(records, key=lambda x: x["date"])
            for r in sorted_records:
                result += f"  • {r['date']}: {r['amount']}元\n"
        
        return MessageEventResult(plain_text=result)

    @filter.command("lst")
    async def total_income(self, event: AstrMessageEvent):
        """计算总收入"""
        if not self.data:
            return MessageEventResult(plain_text="📊暂无收入记录")
        
        total = sum(record["amount"] for record in self.data)
        return MessageEventResult(plain_text=f"📊总收入: {total}元")

    @filter.command("help")
    async def show_help(self, event: AstrMessageEvent):
        """显示帮助信息"""
        help_text = """💰记账本插件帮助:
/+ 类目 金额 [日期] - 添加收入记录(日期可选，默认今天)
/t 日期 - 按天查询收入
/z 起始日期 - 按周查询收入
/y 月份 - 按月查询收入
/++ 年份 - 按年查询收入
/ls - 查看收入类目分布统计
/lsd - 查看收入类目详细记录
/lst - 查看总收入
/help - 显示帮助信息

📌推荐用法:
/+ 工资 5000          # 自动记录今天的收入
/+ 奖金 3000 2025-05-10  # 指定日期

📌统计示例:
/ls                  # 查看类目分布
/lsd                 # 查看类目详细记录
"""
        return MessageEventResult(plain_text=help_text)    
