from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import json
from datetime import datetime, timedelta
import os
from typing import List, Dict

@register("account_book", "YourName", "记账本插件", "1.0.1")
class AccountBookPlugin(Star):
    def __init__(self, context: Context):
        # 必须先调用父类初始化
        super().__init__(context)
        
        # 初始化数据存储
        self._records: List[Dict] = []
        
        # 设置数据文件路径
        self._data_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "account_data.json"
        )
        
        # 加载现有数据
        self._load_data()

    def _load_data(self) -> None:
        """安全加载数据"""
        try:
            if os.path.exists(self._data_file):
                with open(self._data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._records = [
                            record for record in data 
                            if self._validate_record(record)
                        ]
                        logger.info(f"成功加载 {len(self._records)} 条记录")
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
        except Exception as e:
            logger.error(f"保存数据时出错: {str(e)}")

    def _validate_record(self, record: Dict) -> bool:
        """验证记录格式"""
        try:
            if not isinstance(record, dict):
                return False
                
            # 检查必需字段
            required = ["date", "category", "amount"]
            if not all(field in record for field in required):
                return False
                
            # 验证日期格式
            datetime.strptime(record["date"], "%Y-%m-%d")
            
            # 验证金额
            float(record["amount"])
            
            return True
        except (ValueError, TypeError):
            return False

    @filter.command("+")
    async def add_record(self, event: AstrMessageEvent, *args: str) -> MessageEventResult:
        """添加记录 [+ 类别 金额 (日期)]"""
        if len(args) < 2:
            return MessageEventResult(plain_text="❌ 格式: /+ 类别 金额 [日期]\n例: /+ 工资 5000")

        category = args[0]
        
        try:
            amount = float(args[1])
            if amount <= 0:
                return MessageEventResult(plain_text="❌ 金额必须大于0")
        except ValueError:
            return MessageEventResult(plain_text="❌ 金额必须是数字")

        # 处理日期
        date = args[2] if len(args) >= 3 else datetime.now().strftime("%Y-%m-%d")
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return MessageEventResult(plain_text="❌ 日期格式应为YYYY-MM-DD")

        # 添加记录
        self._records.append({
            "date": date,
            "category": category,
            "amount": amount
        })
        self._save_data()
        
        return MessageEventResult(plain_text=f"✅ 已记录: {date} {category} {amount}元")

    @filter.command("查询")
    async def query_records(self, event: AstrMessageEvent, date: str) -> MessageEventResult:
        """查询记录 [查询 YYYY-MM-DD|YYYY-MM|YYYY]"""
        try:
            if "-" in date:
                if len(date.split("-")) == 2:  # 按月查询
                    year, month = map(int, date.split("-"))
                    start = datetime(year, month, 1).date()
                    end = datetime(
                        year if month < 12 else year+1,
                        month+1 if month < 12 else 1,
                        1
                    ).date() - timedelta(days=1)
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
            return MessageEventResult(plain_text="❌ 日期格式错误\n可用格式: YYYY-MM-DD, YYYY-MM, YYYY")

        # 筛选记录
        matched = [
            r for r in self._records
            if start <= datetime.strptime(r["date"], "%Y-%m-%d").date() <= end
        ]
        
        if not matched:
            return MessageEventResult(plain_text=f"📭 {title}没有记录")
            
        # 格式化结果
        total = sum(float(r["amount"]) for r in matched)
        result = [f"📊 {title}记录 (总计: {total:.2f}元)", ""]
        for r in sorted(matched, key=lambda x: x["date"]):
            result.append(f"• {r['date']} {r['category']}: {float(r['amount']):.2f}元")
        
        return MessageEventResult(plain_text="\n".join(result))

    @filter.command("统计")
    async def show_stats(self, event: AstrMessageEvent) -> MessageEventResult:
        """显示统计信息"""
        if not self._records:
            return MessageEventResult(plain_text="📭 暂无记录")
            
        # 按类别统计
        stats = {}
        for r in self._records:
            stats[r["category"]] = stats.get(r["category"], 0) + float(r["amount"])
        
        total = sum(stats.values())
        sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)
        
        # 生成统计
        lines = ["📈 收入统计", f"💰 总收入: {total:.2f}元", ""]
        for category, amount in sorted_stats:
            percent = amount / total * 100
            bar = "▇" * int(percent / 5)  # 每5%一个方块
            lines.append(f"• {category}: {amount:.2f}元 ({percent:.1f}%) {bar}")
        
        return MessageEventResult(plain_text="\n".join(lines))

    @filter.command("帮助")
    async def show_help(self, event: AstrMessageEvent) -> MessageEventResult:
        """显示帮助"""
        help_text = """
💰 记账本使用说明:

/+ 类别 金额 [日期] - 添加记录
/查询 YYYY-MM-DD    - 查询某天
/查询 YYYY-MM       - 查询某月
/查询 YYYY          - 查询某年
/统计               - 查看统计
/帮助               - 显示帮助

示例:
/+ 工资 8000
/+ 奖金 2000 2023-08-15
/查询 2023-08
/统计
"""
        return MessageEventResult(plain_text=help_text.strip())
