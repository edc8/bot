from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import json
from datetime import datetime, timedelta
import os


@register("account_book", "YourName", "一个简单的记账本插件", "1.0.0")
class AccountBookPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_file = "data/account_book_data.json"
        data_dir = os.path.dirname(self.data_file)
        os.makedirs(data_dir, exist_ok=True)
        self._load_data()

    def _load_data(self):
        """加载记账数据"""
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                self.data = json.load(f)
                if not isinstance(self.data, list):
                    logger.warning("数据格式错误，期望列表，重置为空列表")
                    self.data = []
                else:
                    # 进一步验证列表中的每个元素是否为字典
                    valid_data = []
                    for item in self.data:
                        if isinstance(item, dict):
                            valid_data.append(item)
                        else:
                            logger.warning(f"数据项格式错误，跳过: {item}")
                    self.data = valid_data
        except FileNotFoundError:
            self.data = []
        except Exception as e:
            logger.error(f"加载数据失败: {e}")
            self.data = []

    def _save_data(self):
        """保存记账数据"""
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"保存数据失败: {e}")

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

        category = args[0]
        amount = args[1]

        # 验证金额是否为有效数字
        try:
            amount = float(amount)
            if amount <= 0:
                raise ValueError("金额必须大于0")
        except ValueError as e:
            return MessageEventResult(plain_text=f"❌错误：金额必须是大于0的数字！({e})")

        # 处理可选的日期参数
        if len(args) >= 3:
            date = args[2]
            try:
                datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                return MessageEventResult(plain_text="❌日期格式错误，请使用YYYY-MM-DD格式")
        else:
            # 没有提供日期时，自动记录当前日期
            date = datetime.now().strftime("%Y-%m-%d")

        # 创建并添加新记录
        new_record = {
            "date": date,
            "category": category,
            "amount": amount
        }
        self.data.append(new_record)
        self._save_data()

        return MessageEventResult(plain_text=f"✅成功添加收入：{category} {amount}元 ({date})")

    @filter.command_group("查询收入")
    def query_income_group(self):
        """查询收入指令组"""
        pass

    @query_income_group.command("t")
    async def query_income_by_day(self, event: AstrMessageEvent, date: str):
        """按天查询收入

        Args:
            date (str): 日期，格式为YYYY-MM-DD
        """
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return MessageEventResult(plain_text="❌日期格式错误，请使用YYYY-MM-DD格式")

        total_income = 0
        income_list = []

        for record in self.data:
            try:
                record_date = datetime.strptime(record["date"], "%Y-%m-%d")
                if record_date == target_date:
                    total_income += record["amount"]
                    income_list.append(f"• {record['category']}: {record['amount']}元")
            except (KeyError, ValueError):
                continue  # 跳过格式错误的记录

        if income_list:
            result = f"📅{date}收入总计: {total_income}元\n" + "\n".join(income_list)
        else:
            result = f"📅{date}没有收入记录"

        return MessageEventResult(plain_text=result)

    @query_income_group.command("z")
    async def query_income_by_week(self, event: AstrMessageEvent, start_date: str):
        """按周查询收入

        Args:
            start_date (str): 本周起始日期，格式为YYYY-MM-DD
        """
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = start + timedelta(days=6)
        except ValueError:
            return MessageEventResult(plain_text="❌日期格式错误，请使用YYYY-MM-DD格式")

        total_income = 0
        income_list = []

        for record in self.data:
            try:
                record_date = datetime.strptime(record["date"], "%Y-%m-%d")
                if start <= record_date <= end:
                    total_income += record["amount"]
                    income_list.append(f"• {record['date']} {record['category']}: {record['amount']}元")
            except (KeyError, ValueError):
                continue  # 跳过格式错误的记录

        if income_list:
            result = f"📅{start_date}~{end.strptime('%Y-%m-%d')}收入总计: {total_income}元\n" + "\n".join(income_list)
        else:
            result = f"📅{start_date}~{end.strptime('%Y-%m-%d')}没有收入记录"

        return MessageEventResult(plain_text=result)

    @query_income_group.command("y")
    async def query_income_by_month(self, event: AstrMessageEvent, month: str):
        """按月查询收入

        Args:
            month (str): 月份，格式为YYYY-MM
        """
        try:
            target_month = datetime.strptime(month, "%Y-%m")
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
            try:
                record_date = datetime.strptime(record["date"], "%Y-%m-%d")
                if start <= record_date <= end:
                    total_income += record["amount"]
                    income_list.append(f"• {record['date']} {record['category']}: {record['amount']}元")
            except (KeyError, ValueError):
                continue  # 跳过格式错误的记录

        if income_list:
            result = f"📅{month}收入总计: {total_income}元\n" + "\n".join(income_list)
        else:
            result = f"📅{month}没有收入记录"

        return MessageEventResult(plain_text=result)

    @query_income_group.command("++")
    async def query_income_by_year(self, event: AstrMessageEvent, year: str):
        """按年查询收入

        Args:
            year (str): 年份，格式为YYYY
        """
        try:
            target_year = datetime.strptime(year, "%Y")
            start = target_year.replace(month=1, day=1)
            end = target_year.replace(year=target_year.year + 1, month=1, day=1) - timedelta(days=1)
        except ValueError:
            return MessageEventResult(plain_text="❌日期格式错误，请使用YYYY格式")

        total_income = 0
        income_list = []

        for record in self.data:
            try:
                record_date = datetime.strptime(record["date"], "%Y-%m-%d")
                if start <= record_date <= end:
                    total_income += record["amount"]
                    income_list.append(f"• {record['date'][:7]} {record['category']}: {record['amount']}元")
            except (KeyError, ValueError):
                continue  # 跳过格式错误的记录

        if income_list:
            result = f"📅{year}收入总计: {total_income}元\n" + "\n".join(income_list)
        else:
            result = f"📅{year}没有收入记录"

        return MessageEventResult(plain_text=result)

    @filter.command("ls")
    async def list_categories(self, event: AstrMessageEvent):
        """列出所有收入类目及详细统计"""
        if not self.data:
            return MessageEventResult(plain_text="📊暂无收入记录")

        # 按类目统计总收入
        categories = {}
        for record in self.data:
            try:
                cat = record["category"]
                categories[cat] = categories.get(cat, 0) + record["amount"]
            except (KeyError, TypeError):
                continue  # 跳过格式错误的记录

        if not categories:
            return MessageEventResult(plain_text="📊暂无有效收入记录")

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
            try:
                cat = record["category"]
                if cat not in category_data:
                    category_data[cat] = []
                category_data[cat].append(record)
            except KeyError:
                continue  # 跳过格式错误的记录

        if not category_data:
            return MessageEventResult(plain_text="📊暂无有效收入记录")

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

        total = sum(record.get("amount", 0) for record in self.data)

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
