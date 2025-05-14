from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import json
from datetime import datetime, timedelta
import os
from typing import List, Dict, Optional

@register("account_book", "YourName", "一个功能完善的记账本插件", "1.1.0")
class AccountBookPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        
        # 初始化数据文件路径
        self._data_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "data"
        )
        self._data_file = os.path.join(self._data_dir, "account_records.json")
        
        # 确保数据目录存在
        os.makedirs(self._data_dir, exist_ok=True)
        
        # 加载数据
        self._records: List[Dict] = []
        self._load_data()

    def _load_data(self) -> None:
        """从文件加载记账数据"""
        try:
            if os.path.exists(self._data_file):
                with open(self._data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._records = [record for record in data if self._validate_record(record)]
                        logger.info(f"成功加载 {len(self._records)} 条有效记录")
                    else:
                        logger.warning("数据文件格式不正确，将使用空列表")
        except json.JSONDecodeError:
            logger.error("数据文件解析失败，可能是格式错误")
        except Exception as e:
            logger.error(f"加载数据时发生错误: {str(e)}")

    def _save_data(self) -> None:
        """保存数据到文件"""
        try:
            with open(self._data_file, "w", encoding="utf-8") as f:
                json.dump(self._records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存数据时发生错误: {str(e)}")

    def _validate_record(self, record: Dict) -> bool:
        """验证记录格式是否正确"""
        try:
            required_fields = {"date", "category", "amount"}
            if not all(field in record for field in required_fields):
                return False
            
            # 验证日期格式
            datetime.strptime(record["date"], "%Y-%m-%d")
            
            # 验证金额是有效数字
            float(record["amount"])
            
            return True
        except (ValueError, KeyError, TypeError):
            return False

    @filter.command("+")
    async def add_record(self, event: AstrMessageEvent, *args: str) -> MessageEventResult:
        """
        添加收入记录
        用法: /+ 类别 金额 [日期]
        示例: /+ 工资 5000
              /+ 奖金 3000 2023-08-15
        """
        if len(args) < 2:
            return MessageEventResult(plain_text="❌ 参数不足！请提供类别和金额\n示例: /+ 工资 5000")

        category = args[0]
        
        try:
            amount = float(args[1])
            if amount <= 0:
                return MessageEventResult(plain_text="❌ 金额必须大于0")
        except ValueError:
            return MessageEventResult(plain_text="❌ 金额必须是数字")

        # 处理日期参数
        if len(args) >= 3:
            try:
                datetime.strptime(args[2], "%Y-%m-%d")
                date = args[2]
            except ValueError:
                return MessageEventResult(plain_text="❌ 日期格式错误，请使用YYYY-MM-DD格式")
        else:
            date = datetime.now().strftime("%Y-%m-%d")

        # 创建新记录
        new_record = {
            "date": date,
            "category": category,
            "amount": amount
        }
        
        self._records.append(new_record)
        self._save_data()
        
        return MessageEventResult(plain_text=f"✅ 成功添加记录: {date} {category} {amount}元")

    @filter.command_group("查询")
    def query_group(self):
        """查询命令组"""
        pass

    @query_group.command("天")
    async def query_daily(self, event: AstrMessageEvent, date: str) -> MessageEventResult:
        """按天查询记录 用法: /查询天 2023-08-15"""
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            return MessageEventResult(plain_text="❌ 日期格式错误，请使用YYYY-MM-DD格式")

        daily_records = [
            r for r in self._records 
            if datetime.strptime(r["date"], "%Y-%m-%d").date() == target_date
        ]
        
        return self._format_query_result(f"{date}的收入记录", daily_records)

    @query_group.command("月")
    async def query_monthly(self, event: AstrMessageEvent, month: str) -> MessageEventResult:
        """按月查询记录 用法: /查询月 2023-08"""
        try:
            year, month = map(int, month.split("-"))
            start_date = datetime(year, month, 1).date()
            if month == 12:
                end_date = datetime(year+1, 1, 1).date() - timedelta(days=1)
            else:
                end_date = datetime(year, month+1, 1).date() - timedelta(days=1)
        except ValueError:
            return MessageEventResult(plain_text="❌ 月份格式错误，请使用YYYY-MM格式")

        monthly_records = [
            r for r in self._records 
            if start_date <= datetime.strptime(r["date"], "%Y-%m-%d").date() <= end_date
        ]
        
        return self._format_query_result(f"{month}月的收入记录", monthly_records)

    @query_group.command("年")
    async def query_yearly(self, event: AstrMessageEvent, year: str) -> MessageEventResult:
        """按年查询记录 用法: /查询年 2023"""
        try:
            year = int(year)
            start_date = datetime(year, 1, 1).date()
            end_date = datetime(year+1, 1, 1).date() - timedelta(days=1)
        except ValueError:
            return MessageEventResult(plain_text="❌ 年份格式错误，请使用YYYY格式")

        yearly_records = [
            r for r in self._records 
            if start_date <= datetime.strptime(r["date"], "%Y-%m-%d").date() <= end_date
        ]
        
        return self._format_query_result(f"{year}年的收入记录", yearly_records)

    def _format_query_result(self, title: str, records: List[Dict]) -> MessageEventResult:
        """格式化查询结果"""
        if not records:
            return MessageEventResult(plain_text=f"📭 没有找到{title}")

        total = sum(float(r["amount"]) for r in records)
        result = [f"📊 {title} (总计: {total:.2f}元)", ""]
        
        # 按日期排序
        sorted_records = sorted(records, key=lambda x: x["date"])
        
        for record in sorted_records:
            result.append(
                f"• {record['date']} {record['category']}: {float(record['amount']):.2f}元"
            )
        
        return MessageEventResult(plain_text="\n".join(result))

    @filter.command("统计")
    async def show_statistics(self, event: AstrMessageEvent) -> MessageEventResult:
        """显示统计信息"""
        if not self._records:
            return MessageEventResult(plain_text="📭 还没有任何记录")

        # 按类别统计
        category_stats = {}
        for record in self._records:
            category = record["category"]
            amount = float(record["amount"])
            category_stats[category] = category_stats.get(category, 0) + amount

        total = sum(category_stats.values())
        sorted_categories = sorted(
            category_stats.items(), 
            key=lambda x: x[1], 
            reverse=True
        )

        # 生成统计结果
        result = ["📈 收入统计", f"💰 总收入: {total:.2f}元", ""]
        
        for category, amount in sorted_categories:
            percentage = amount / total * 100
            bar = "▇" * int(percentage / 5)  # 每5%一个方块
            result.append(
                f"• {category}: {amount:.2f}元 ({percentage:.1f}%) {bar}"
            )
        
        return MessageEventResult(plain_text="\n".join(result))

    @filter.command("帮助")
    async def show_help(self, event: AstrMessageEvent) -> MessageEventResult:
        """显示帮助信息"""
        help_text = """
💰 记账本插件使用帮助:

基本命令:
/+ 类别 金额 [日期] - 添加收入记录(日期可选)
/查询天 YYYY-MM-DD - 查询某天的记录
/查询月 YYYY-MM - 查询某月的记录
/查询年 YYYY - 查询某年的记录
/统计 - 查看收入统计
/帮助 - 显示本帮助

示例:
/+ 工资 8000
/+ 奖金 2000 2023-08-15
/查询月 2023-08
/统计
"""
        return MessageEventResult(plain_text=help_text.strip())
