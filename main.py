from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import json
from datetime import datetime
import os
from typing import List, Dict

@register("account_book", "FinanceBot", "一个简单的记账插件", "1.0.0")
class AccountBookPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._records_file = os.path.join(context.get_plugin_data_dir(), "records.json")
        self._records = self._load_records()
        logger.info("记账插件初始化完成")

    def _load_records(self) -> List[Dict]:
        """加载历史记录"""
        try:
            if os.path.exists(self._records_file):
                with open(self._records_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return []
        except Exception as e:
            logger.error(f"加载记录失败: {e}")
            return []

    def _save_records(self) -> None:
        """保存记录"""
        try:
            with open(self._records_file, 'w', encoding='utf-8') as f:
                json.dump(self._records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存记录失败: {e}")

    @filter.command("记账")
    async def add_record(self, event: AstrMessageEvent):
        """添加一条记账记录
        使用方式: /记账 早餐 -15 今天早上买了包子
        """
        parts = event.message_str.split()[1:]  # 去掉命令名
        if len(parts) < 2:
            yield event.plain_result("❌ 格式错误，正确格式: /记账 分类 金额 [备注]")
            return

        category = parts[0]
        
        try:
            amount = float(parts[1])
        except ValueError:
            yield event.plain_result("❌ 金额必须是数字")
            return

        remark = ' '.join(parts[2:]) if len(parts) > 2 else ""
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self._records.append({
            "date": date,
            "category": category,
            "amount": amount,
            "remark": remark
        })
        self._save_records()

        yield event.plain_result(f"✅ 已记录: {category} {amount}元{' - ' + remark if remark else ''}")

    @filter.command("查询")
    async def query_records(self, event: AstrMessageEvent):
        """查询记账记录
        使用方式: 
          /查询 - 查看所有记录
          /查询 餐饮 - 查看餐饮分类的记录
        """
        parts = event.message_str.split()[1:]
        keyword = parts[0] if parts else None

        filtered_records = self._records
        if keyword:
            filtered_records = [r for r in self._records 
                               if keyword in r["category"] or keyword in r["remark"]]

        if not filtered_records:
            yield event.plain_result("📭 没有找到相关记录")
            return

        result = ["📒 记账记录:"]
        for record in filtered_records:
            result.append(f"{record['date']} | {record['category']} | {record['amount']}元" +
                         (f" | {record['remark']}" if record['remark'] else ""))

        yield event.plain_result("\n".join(result))

    @filter.command("统计")
    async def show_stats(self, event: AstrMessageEvent):
        """统计各类支出和总收入"""
        if not self._records:
            yield event.plain_result("📭 暂无记录")
            return

        category_stats = {}
        total_income = 0
        total_expense = 0

        for record in self._records:
            amount = record["amount"]
            category = record["category"]
            
            if amount > 0:
                total_income += amount
            else:
                total_expense += abs(amount)

            category_stats[category] = category_stats.get(category, 0) + amount

        result = ["📊 统计结果:"]
        result.append(f"总收入: {total_income:.2f}元")
        result.append(f"总支出: {total_expense:.2f}元")
        result.append("")
        result.append("分类统计:")
        
        for category, amount in category_stats.items():
            result.append(f"{category}: {amount:.2f}元")

        yield event.plain_result("\n".join(result))

    @filter.command("帮助")
    async def show_help(self, event: AstrMessageEvent):
        """显示帮助信息"""
        help_text = """
📕 记账插件使用帮助:

1. 添加记录:
   /记账 分类 金额 [备注]
   示例: /记账 早餐 -15 今天早上买了包子

2. 查询记录:
   /查询 [关键词]
   示例: 
     /查询 - 查看所有记录
     /查询 餐饮 - 查看餐饮分类的记录

3. 统计:
   /统计 - 查看各类支出和总收入

4. 帮助:
   /帮助 - 显示此帮助信息
"""
        yield event.plain_result(help_text.strip())

    async def terminate(self):
        """插件卸载时调用"""
        self._save_records()
        logger.info("记账插件已卸载")
