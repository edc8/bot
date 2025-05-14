from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from datetime import datetime
from typing import Dict, List, Optional
import json
import os

@register("accounting", "YourName", "一个简单的记账插件", "1.0.0")
class AccountingPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_file = "accounting_data.json"
        self.records: Dict[str, List[Dict]] = {}  # 用户ID -> 账单记录列表
        self.categories = {
            "收入": ["工资", "奖金", "投资", "其他收入"],
            "支出": ["餐饮", "购物", "交通", "娱乐", "住房", "医疗", "教育", "其他支出"]
        }

    async def initialize(self):
        """加载保存的记账数据"""
        if os.path.exists(self.data_file):
            with open(self.data_file, "r", encoding="utf-8") as f:
                self.records = json.load(f)
        logger.info("记账插件初始化完成")

    def _save_data(self):
        """保存数据到文件"""
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(self.records, f, ensure_ascii=False, indent=2)

    @filter.command("记账帮助")
    async def accounting_help(self, event: AstrMessageEvent):
        """显示记账帮助信息"""
        help_text = """记账插件使用说明:
/记录收入 [金额] [类别] [备注] - 记录一笔收入
/记录支出 [金额] [类别] [备注] - 记录一笔支出
/查询账单 [天数] - 查询最近N天的账单(默认7天)
/账单统计 [天数] - 统计最近N天的收支情况
/删除记录 [序号] - 删除指定序号的记录
/记账帮助 - 显示此帮助信息

可用类别:
收入: """ + "、".join(self.categories["收入"]) + """
支出: """ + "、".join(self.categories["支出"])
        yield event.plain_result(help_text)

    @filter.command("记录收入")
    async def add_income(self, event: AstrMessageEvent):
        """记录一笔收入"""
        user_id = event.get_sender_id()
        parts = event.message_str.split(maxsplit=2)
        
        if len(parts) < 2:
            yield event.plain_result("格式错误，请使用: /记录收入 [金额] [类别] [备注(可选)]")
            return
        
        try:
            amount = float(parts[0])
            category = parts[1]
            note = parts[2] if len(parts) > 2 else ""
            
            if category not in self.categories["收入"]:
                yield event.plain_result(f"无效的收入类别，可用类别: {'、'.join(self.categories['收入'])}")
                return
                
            record = {
                "type": "收入",
                "amount": amount,
                "category": category,
                "note": note,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            if user_id not in self.records:
                self.records[user_id] = []
                
            self.records[user_id].append(record)
            self._save_data()
            yield event.plain_result(f"已记录收入: {amount}元 ({category}) {note}")
            
        except ValueError:
            yield event.plain_result("金额必须是数字")

    @filter.command("记录支出")
    async def add_expense(self, event: AstrMessageEvent):
        """记录一笔支出"""
        user_id = event.get_sender_id()
        parts = event.message_str.split(maxsplit=2)
        
        if len(parts) < 2:
            yield event.plain_result("格式错误，请使用: /记录支出 [金额] [类别] [备注(可选)]")
            return
        
        try:
            amount = float(parts[0])
            category = parts[1]
            note = parts[2] if len(parts) > 2 else ""
            
            if category not in self.categories["支出"]:
                yield event.plain_result(f"无效的支出类别，可用类别: {'、'.join(self.categories['支出'])}")
                return
                
            record = {
                "type": "支出",
                "amount": amount,
                "category": category,
                "note": note,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            if user_id not in self.records:
                self.records[user_id] = []
                
            self.records[user_id].append(record)
            self._save_data()
            yield event.plain_result(f"已记录支出: {amount}元 ({category}) {note}")
            
        except ValueError:
            yield event.plain_result("金额必须是数字")

    @filter.command("查询账单")
    async def query_records(self, event: AstrMessageEvent):
        """查询账单记录"""
        user_id = event.get_sender_id()
        days = 7  # 默认查询7天
        
        parts = event.message_str.split()
        if parts and parts[0].isdigit():
            days = min(int(parts[0]), 30)  # 最多查询30天
            
        if user_id not in self.records or not self.records[user_id]:
            yield event.plain_result("您还没有任何记账记录")
            return
            
        now = datetime.now()
        records = [
            r for r in self.records[user_id]
            if (now - datetime.strptime(r["time"], "%Y-%m-%d %H:%M:%S")).days <= days
        ]
        
        if not records:
            yield event.plain_result(f"最近{days}天内没有记账记录")
            return
            
        result = [f"最近{days}天的账单记录:"]
        for i, record in enumerate(records, 1):
            result.append(
                f"{i}. [{record['type']}] {record['amount']}元 ({record['category']}) "
                f"{record['note']} {record['time']}"
            )
            
        yield event.plain_result("\n".join(result))

    @filter.command("账单统计")
    async def stats_records(self, event: AstrMessageEvent):
        """统计账单数据"""
        user_id = event.get_sender_id()
        days = 7  # 默认统计7天
        
        parts = event.message_str.split()
        if parts and parts[0].isdigit():
            days = min(int(parts[0]), 30)  # 最多统计30天
            
        if user_id not in self.records or not self.records[user_id]:
            yield event.plain_result("您还没有任何记账记录")
            return
            
        now = datetime.now()
        records = [
            r for r in self.records[user_id]
            if (now - datetime.strptime(r["time"], "%Y-%m-%d %H:%M:%S")).days <= days
        ]
        
        if not records:
            yield event.plain_result(f"最近{days}天内没有记账记录")
            return
            
        income = sum(r["amount"] for r in records if r["type"] == "收入")
        expense = sum(r["amount"] for r in records if r["type"] == "支出")
        balance = income - expense
        
        # 按类别统计
        income_by_cat = {}
        expense_by_cat = {}
        
        for r in records:
            if r["type"] == "收入":
                income_by_cat[r["category"]] = income_by_cat.get(r["category"], 0) + r["amount"]
            else:
                expense_by_cat[r["category"]] = expense_by_cat.get(r["category"], 0) + r["amount"]
        
        result = [
            f"最近{days}天账单统计:",
            f"总收入: {income:.2f}元",
            f"总支出: {expense:.2f}元",
            f"净收入: {balance:.2f}元",
            "\n收入分类统计:"
        ]
        
        for cat, amount in income_by_cat.items():
            result.append(f"- {cat}: {amount:.2f}元")
            
        result.append("\n支出分类统计:")
        for cat, amount in expense_by_cat.items():
            result.append(f"- {cat}: {amount:.2f}元")
            
        yield event.plain_result("\n".join(result))

    @filter.command("删除记录")
    async def delete_record(self, event: AstrMessageEvent):
        """删除指定记录"""
        user_id = event.get_sender_id()
        
        if user_id not in self.records or not self.records[user_id]:
            yield event.plain_result("您还没有任何记账记录")
            return
            
        try:
            index = int(event.message_str.strip()) - 1
            if 0 <= index < len(self.records[user_id]):
                record = self.records[user_id].pop(index)
                self._save_data()
                yield event.plain_result(
                    f"已删除记录: [{record['type']}] {record['amount']}元 "
                    f"({record['category']}) {record['note']}"
                )
            else:
                yield event.plain_result("无效的记录序号")
        except ValueError:
            yield event.plain_result("请提供有效的记录序号")

    async def terminate(self):
        """插件卸载时保存数据"""
        self._save_data()
        logger.info("记账插件已卸载")
