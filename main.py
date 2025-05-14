from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import json
from datetime import datetime, timedelta
import os
from typing import List, Dict, Optional

@register("account_book", "FinanceBot", "多功能记账本插件", "1.1.1")
class AccountBookPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        
        # 初始化数据存储
        self._records: List[Dict] = []
        
        # 设置数据文件路径
        self._plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self._data_file = os.path.join(self._plugin_dir, "account_data.json")
        
        # 加载现有数据
        self._load_data()
        logger.info("记账本插件初始化完成")

    def _load_data(self) -> None:
        """安全加载数据文件"""
        try:
            if os.path.exists(self._data_file):
                with open(self._data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._records = [r for r in data if self._validate_record(r)]
                        logger.info(f"已加载 {len(self._records)} 条有效记录")
                    else:
                        logger.warning("数据文件格式不正确，将初始化空列表")
        except json.JSONDecodeError:
            logger.error("数据文件解析失败，将初始化空列表")
        except Exception as e:
            logger.error(f"加载数据时出错: {str(e)}")

    def _save_data(self) -> None:
        """保存数据到文件"""
        try:
            with open(self._data_file, "w", encoding="utf-8") as f:
                json.dump(self._records, f, ensure_ascii=False, indent=2)
            logger.info("数据保存成功")
        except Exception as e:
            logger.error(f"保存数据失败: {str(e)}")

    def _validate_record(self, record: Dict) -> bool:
        """验证记录格式是否正确"""
        try:
            # 检查必需字段
            if not all(k in record for k in ["date", "category", "amount"]):
                return False
                
            # 验证日期格式
            datetime.strptime(record["date"], "%Y-%m-%d")
            
            # 验证金额
            amount = float(record["amount"])
            if amount <= 0:
                return False
                
            return True
        except (ValueError, TypeError):
            return False

    @filter.command("+")
    async def add_record(self, event: AstrMessageEvent, *args: str) -> MessageEventResult:
        """
        添加收入记录
        格式: /+ 类别 金额 [日期]
        示例: 
          /+ 工资 8000
          /+ 奖金 2000 2023-08-15
        """
        if len(args) < 2:
            return self._show_help("add")

        category = args[0]
        
        try:
            amount = float(args[1])
            if amount <= 0:
                return MessageEventResult(text="❌ 金额必须大于0")
        except ValueError:
            return MessageEventResult(text="❌ 金额必须是正数")

        # 处理日期参数
        date = args[2] if len(args) >= 3 else datetime.now().strftime("%Y-%m-%d")
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return MessageEventResult(text="❌ 日期格式应为YYYY-MM-DD")

        # 添加记录
        self._records.append({
            "date": date,
            "category": category,
            "amount": amount
        })
        self._save_data()
        
        return MessageEventResult(text=f"✅ 记录成功: {date} {category} {amount}元")

    @filter.command("查询")
    async def query_records(self, event: AstrMessageEvent, date: str = None) -> MessageEventResult:
        """
        查询记录
        格式: 
          /查询 YYYY-MM-DD  # 按天
          /查询 YYYY-MM     # 按月
          /查询 YYYY        # 按年
        """
        if not date:
            return self._show_help("query")

        try:
            if "-" in date:
                parts = date.split("-")
                if len(parts) == 2:  # 按月查询
                    year, month = map(int, parts)
                    start = datetime(year, month, 1).date()
                    end = datetime(year + (month==12), (month%12)+1, 1).date() - timedelta(days=1)
                    title = f"{year}年{month}月"
                else:  # 按天查询
                    target = datetime.strptime(date, "%Y-%m-%d").date()
                    start = end = target
                    title = date
            else:  # 按年查询
                year = int(date)
                start = datetime(year, 1, 1).date()
                end = datetime(year+1, 1, 1).date() - timedelta(days=1)
                title = f"{year}年"
        except ValueError:
            return MessageEventResult(text="❌ 日期格式错误\n" + self._show_help("query").text)

        # 筛选记录
        matched = []
        for record in self._records:
            try:
                record_date = datetime.strptime(record["date"], "%Y-%m-%d").date()
                if start <= record_date <= end:
                    matched.append(record)
            except:
                continue

        if not matched:
            return MessageEventResult(text=f"📭 {title}没有记录")
            
        # 格式化结果
        total = sum(float(r["amount"]) for r in matched)
        result = [f"📊 {title} 收入记录 (总计: {total:.2f}元)", ""]
        for r in sorted(matched, key=lambda x: x["date"]):
            result.append(f"• {r['date']} {r['category']}: {float(r['amount']):.2f}元")
        
        return MessageEventResult(text="\n".join(result))

    @filter.command("统计")
    async def show_stats(self, event: AstrMessageEvent) -> MessageEventResult:
        """查看收入统计"""
        if not self._records:
            return MessageEventResult(text="📭 暂无任何记录")

        # 按类别统计
        stats = {}
        for r in self._records:
            stats[r["category"]] = stats.get(r["category"], 0) + float(r["amount"])
        
        total = sum(stats.values())
        sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)
        
        # 生成统计图表
        lines = ["📈 收入统计分析", f"💰 总收入: {total:.2f}元", ""]
        for category, amount in sorted_stats:
            percent = amount / total * 100
            bar = "▇" * int(percent / 3)  # 每3%一个方块
            lines.append(f"• {category}: {amount:.2f}元 ({percent:.1f}%) {bar}")
        
        return MessageEventResult(text="\n".join(lines))

    @filter.command("帮助")
    async def show_help(self, event: AstrMessageEvent) -> MessageEventResult:
        """显示帮助信息"""
        return self._show_help()

    def _show_help(self, cmd_type: str = None) -> MessageEventResult:
        """生成帮助信息"""
        help_texts = {
            "add": """
💰 添加记录帮助:
/+ 类别 金额 [日期]
示例:
  /+ 工资 8000
  /+ 奖金 2000 2023-08-15
注意: 金额必须大于0，日期格式为YYYY-MM-DD
""",
            "query": """
📅 查询记录帮助:
/查询 YYYY-MM-DD  # 查询某天
/查询 YYYY-MM     # 查询某月
/查询 YYYY        # 查询某年
示例:
  /查询 2023-08-15
  /查询 2023-08
  /查询 2023
""",
            "default": """
📒 记账本使用帮助:

基本命令:
/+ 类别 金额 [日期] - 添加记录
/查询 [日期]       - 查询记录
/统计             - 查看统计
/帮助             - 显示帮助

更多帮助:
/帮助 add    - 添加记录帮助
/帮助 query  - 查询记录帮助
"""
        }
        
        if cmd_type in help_texts:
            return MessageEventResult(text=help_texts[cmd_type].strip())
        return MessageEventResult(text=help_texts["default"].strip())

    @filter.command("导出")
    async def export_data(self, event: AstrMessageEvent) -> MessageEventResult:
        """导出所有记录(开发中)"""
        return MessageEventResult(text="⏳ 导出功能开发中，敬请期待")
