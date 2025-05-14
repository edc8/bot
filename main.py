from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from datetime import datetime
import json
import os

@register("accounting", "YourName", "一个简单的记账插件", "1.0.0")
class AccountingPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_file = os.path.join(context.get_plugin_data_dir(), "accounting_data.json")
        self.records = {}
        self.load_data()

    def load_data(self):
        """加载存储的记账数据"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    self.records = json.load(f)
        except Exception as e:
            logger.error(f"加载记账数据失败: {e}")
            self.records = {}

    def save_data(self):
        """保存记账数据"""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存记账数据失败: {e}")

    async def initialize(self):
        """插件初始化"""
        logger.info("记账插件已初始化")

    @filter.command("记账")
    async def add_record(self, event: AstrMessageEvent):
        """记录一笔消费。用法：/记账 金额 类别 备注(可选)"""
        user_id = event.get_sender_id()
        message_parts = event.message_str.strip().split()
        
        if len(message_parts) < 3:
            yield event.plain_result("用法错误！正确格式：/记账 金额 类别 备注(可选)")
            return
            
        try:
            amount = float(message_parts[1])
        except ValueError:
            yield event.plain_result("金额必须是数字！")
            return
            
        category = message_parts[2]
        remark = " ".join(message_parts[3:]) if len(message_parts) > 3 else ""
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if user_id not in self.records:
            self.records[user_id] = []
            
        record = {
            "amount": amount,
            "category": category,
            "remark": remark,
            "date": date_str
        }
        
        self.records[user_id].append(record)
        self.save_data()
        
        yield event.plain_result(f"已记录: {amount}元，类别: {category}，备注: {remark}")

    @filter.command("记账列表")
    async def list_records(self, event: AstrMessageEvent):
        """查看消费记录列表。用法：/记账列表 [最近N条记录，默认10条]"""
        user_id = event.get_sender_id()
        message_parts = event.message_str.strip().split()
        
        count = 10
        if len(message_parts) > 1:
            try:
                count = int(message_parts[1])
                if count <= 0:
                    count = 10
            except ValueError:
                pass
                
        if user_id not in self.records or not self.records[user_id]:
            yield event.plain_result("暂无消费记录")
            return
            
        records = self.records[user_id][-count:]
        records_text = "\n".join([
            f"{i+1}. {r['date']} - {r['amount']}元 - {r['category']} - {r['remark']}"
            for i, r in enumerate(records)
        ])
        
        yield event.plain_result(f"最近{count}条消费记录:\n{records_text}")

    @filter.command("记账统计")
    async def statistics(self, event: AstrMessageEvent):
        """查看消费统计。用法：/记账统计 [类别(可选)]"""
        user_id = event.get_sender_id()
        message_parts = event.message_str.strip().split()
        
        if user_id not in self.records or not self.records[user_id]:
            yield event.plain_result("暂无消费记录")
            return
            
        category = message_parts[1] if len(message_parts) > 1 else None
        user_records = self.records[user_id]
        
        if category:
            # 按类别统计
            category_records = [r for r in user_records if r["category"] == category]
            if not category_records:
                yield event.plain_result(f"没有找到类别为'{category}'的消费记录")
                return
                
            total = sum(r["amount"] for r in category_records)
            yield event.plain_result(f"类别 '{category}' 的消费统计:\n总金额: {total}元\n记录数: {len(category_records)}条")
        else:
            # 全部统计
            total = sum(r["amount"] for r in user_records)
            categories = {}
            for r in user_records:
                cat = r["category"]
                categories[cat] = categories.get(cat, 0) + r["amount"]
                
            categories_text = "\n".join([f"{k}: {v}元" for k, v in categories.items()])
            
            yield event.plain_result(f"消费总览:\n总金额: {total}元\n记录数: {len(user_records)}条\n按类别统计:\n{categories_text}")

    async def terminate(self):
        """插件销毁"""
        self.save_data()
        logger.info("记账插件已停用")
