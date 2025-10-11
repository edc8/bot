from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from typing import Dict, List, Optional, Tuple
import json
import os
import time
import uuid
from datetime import datetime


@register(
    "aa_settlement",  # 插件名称
    "anchor",          # 作者
    "专业AA分账系统（支持多人分账、明细管理、清账跟踪）",  # 描述
    "2.0.0"            # 版本
)
class AASettlementPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 核心数据结构
        self.aa_bills: Dict[str, List[Dict]] = {}  # 按用户ID存储AA账单，key=user_id，value=账单列表
        self.settlement_records: Dict[str, List[Dict]] = {}  # 清账记录，key=user_id，value=清账记录列表
        
        # 数据持久化路径（插件目录下）
        self.bills_data_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 
            "aa_bills.json"
        )
        self.settlement_data_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 
            "settlement_records.json"
        )
        
        # 初始化加载数据
        self._load_bills_data()
        self._load_settlement_data()

    # ---------------------- 主指令组 ----------------------
    @filter.command_group("aa")
    def aa_main_group(self):
        """AA分账主指令组，所有分账功能通过该指令触发"""
        pass

    # ---------------------- 核心功能：账单创建 ----------------------
    @aa_main_group.command("create")
    async def create_aa_bill(self, event: AstrMessageEvent, *args):
        """
        创建AA账单
        指令格式：/aa create [参与人1] [参与人2] ... [总金额] [消费描述]
        示例：/aa create 张三 李四 王五 600 聚餐
        """
        # 基础参数验证
        if len(args) < 3:
            yield event.plain_result(
                "❌ 指令格式错误！正确用法：\n"
                "📌 /aa create [参与人1] [参与人2] ... [总金额] [消费描述]\n"
                "示例：/aa create 张三 李四 王五 600 聚餐（3人AA，总600元）"
            )
            return

        # 解析参数（最后两位分别是总金额和消费描述，前面是参与人）
        try:
            total_amount = float(args[-2])  # 总金额（倒数第二个参数）
            if total_amount <= 0:
                raise ValueError("总金额必须大于0")
        except ValueError as e:
            yield event.plain_result(f"❌ 金额错误：{str(e)}（请输入正数，支持小数）")
            return

        consumption_desc = args[-1]  # 消费描述（最后一个参数）
        participants = list(args[:-2])  # 参与人列表（除了最后两位的所有参数）
        
        # 补充付款人（当前指令发送者）到参与人列表
        payer_id = event.get_sender_id()
        payer_name = event.get_sender_name() or f"用户{payer_id[:4]}"  # 若获取不到昵称，用用户ID前4位
        if payer_name not in participants:
            participants.append(payer_name)
        
        # 去重（避免重复添加同一参与人）
        participants = list(set(participants))
        total_people = len(participants)
        
        # 计算每人分摊金额（保留2位小数）
        per_person_amount = round(total_amount / total_people, 2)
        
        # 处理分账误差（当总金额无法被人数整除时，误差由付款人承担）
        calculated_total = round(per_person_amount * total_people, 2)
        amount_diff = round(total_amount - calculated_total, 2)

        # 生成账单基础信息
        bill_id = str(uuid.uuid4())[:6]  # 账单ID（UUID前6位，简短易记）
        create_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # 创建时间
        create_timestamp = int(time.time())  # 时间戳（用于排序）

        # 构建账单详情
        bill_detail = {
            "bill_id": bill_id,
            "payer": {
                "id": payer_id,
                "name": payer_name
            },
            "total_amount": round(total_amount, 2),
            "consumption_desc": consumption_desc,
            "participants": participants,
            "total_people": total_people,
            "per_person_amount": per_person_amount,
            "amount_diff": amount_diff,  # 分账误差（可为0）
            "status": "pending",  # 账单状态：pending=待清账，cleared=已清账
            "create_time": create_time,
            "create_timestamp": create_timestamp,
            "clear_time": None,  # 清账时间（待清账时为None）
            "clearer": None,  # 清账人（待清账时为None）
            "debt_details": self._generate_debt_details(
                payer_name, participants, per_person_amount
            )  # 债务明细（谁该给谁多少钱）
        }

        # 保存账单到当前用户的账单列表
        self.aa_bills.setdefault(payer_id, []).append(bill_detail)
        self._save_bills_data()

        # 生成返回结果
        result = (
            "✅ AA账单创建成功！\n"
            "=" * 40 + "\n"
            f"🆔 账单ID：{bill_id}\n"
            f"💸 付款人：{payer_name}\n"
            f"📝 消费描述：{consumption_desc}\n"
            f"💰 总金额：{bill_detail['total_amount']}元\n"
            f"👥 参与人（共{total_people}人）：{', '.join(participants)}\n"
            f"🧮 每人分摊：{per_person_amount}元\n"
        )
        if amount_diff > 0:
            result += f"⚠️  分账误差：{payer_name}多承担{amount_diff}元（总金额无法均分）\n"
        result += (
            f"⏰ 创建时间：{create_time}\n"
            "=" * 40 + "\n"
            "💡 后续操作：\n"
            f"  1. 查看账单：/aa list\n"
            f"  2. 标记清账：/aa clear {bill_id}\n"
            f"  3. 查看债务：/aa debt {bill_id}"
        )
        yield event.plain_result(result)

    # ---------------------- 核心功能：账单管理 ----------------------
    @aa_main_group.command("list")
    async def list_aa_bills(self, event: AstrMessageEvent, status: Optional[str] = None):
        """
        查看AA账单列表
        指令格式：/aa list [状态]（状态可选：pending=待清账，cleared=已清账，默认显示全部）
        示例：/aa list（查看所有账单）、/aa list pending（仅查看待清账）
        """
        user_id = event.get_sender_id()
        user_bills = self.aa_bills.get(user_id, [])
        
        # 无账单时的提示
        if not user_bills:
            yield event.plain_result(
                "📋 暂无AA账单\n"
                "💡 点击创建：/aa create [参与人1] [参与人2] ... [金额] [描述]\n"
                "示例：/aa create 张三 李四 300 下午茶"
            )
            return

        # 按状态筛选账单（默认显示全部）
        if status == "pending":
            filtered_bills = [b for b in user_bills if b["status"] == "pending"]
            title = f"🔴 待清账账单（共{len(filtered_bills)}条）"
        elif status == "cleared":
            filtered_bills = [b for b in user_bills if b["status"] == "cleared"]
            title = f"🟢 已清账账单（共{len(filtered_bills)}条）"
        else:
            filtered_bills = user_bills
            pending_count = len([b for b in user_bills if b["status"] == "pending"])
            cleared_count = len([b for b in user_bills if b["status"] == "cleared"])
            title = f"📊 所有AA账单（待清账：{pending_count}条 | 已清账：{cleared_count}条）"

        # 按创建时间倒序排序（最新的在前）
        sorted_bills = sorted(
            filtered_bills, 
            key=lambda x: x["create_timestamp"], 
            reverse=True
        )[:10]  # 最多显示10条（避免信息过长）

        # 构建账单列表输出
        result = title + "\n" + "-" * 50 + "\n"
        for idx, bill in enumerate(sorted_bills, 1):
            status_tag = "🔴 待清账" if bill["status"] == "pending" else "🟢 已清账"
            clear_info = f"清账时间：{bill['clear_time']}" if bill["status"] == "cleared" else "操作：/aa clear " + bill["bill_id"]
            
            result += (
                f"{idx}. 账单ID：{bill['bill_id']} | {status_tag}\n"
                f"   消费描述：{bill['consumption_desc']}\n"
                f"   付款人：{bill['payer']['name']} | 总金额：{bill['total_amount']}元\n"
                f"   参与人：{', '.join(bill['participants'])}（{bill['total_people']}人）\n"
                f"   创建时间：{bill['create_time']}\n"
                f"   {clear_info}\n"
                "-" * 50 + "\n"
            )

        # 补充提示信息
        if len(sorted_bills) >= 10:
            result += "⚠️  仅显示最近10条账单，如需查看更多请联系开发者\n"
        result += "💡 查看债务明细：/aa debt [账单ID]（示例：/aa debt abc123）"
        
        yield event.plain_result(result)

    @aa_main_group.command("clear")
    async def clear_aa_bill(self, event: AstrMessageEvent, bill_id: str):
        """
        标记AA账单为已清账
        指令格式：/aa clear [账单ID]
        示例：/aa clear abc123（将ID为abc123的账单标记为已清账）
        """
        user_id = event.get_sender_id()
        user_bills = self.aa_bills.get(user_id, [])
        clearer_name = event.get_sender_name() or f"用户{user_id[:4]}"
        clear_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 查找目标账单
        target_bill = None
        for bill in user_bills:
            if bill["bill_id"] == bill_id:
                target_bill = bill
                break

        # 账单不存在的处理
        if not target_bill:
            yield event.plain_result(f"❌ 未找到ID为「{bill_id}」的AA账单\n"
                                    "💡 查看所有账单：/aa list")
            return

        # 已清账的处理
        if target_bill["status"] == "cleared":
            yield event.plain_result(
                f"✅ 账单「{bill_id}」已是已清账状态\n"
                f"清账时间：{target_bill['clear_time']}\n"
                f"清账人：{target_bill['clearer']['name']}"
            )
            return

        # 标记为已清账并更新信息
        target_bill["status"] = "cleared"
        target_bill["clear_time"] = clear_time
        target_bill["clearer"] = {
            "id": user_id,
            "name": clearer_name
        }

        # 保存清账记录
        settlement_record = {
            "record_id": str(uuid.uuid4())[:8],
            "bill_id": bill_id,
            "bill_desc": target_bill["consumption_desc"],
            "total_amount": target_bill["total_amount"],
            "clearer": {
                "id": user_id,
                "name": clearer_name
            },
            "clear_time": clear_time,
            "timestamp": int(time.time())
        }
        self.settlement_records.setdefault(user_id, []).append(settlement_record)

        # 持久化数据
        self._save_bills_data()
        self._save_settlement_data()

        # 生成清账成功结果
        result = (
            f"✅ 账单「{bill_id}」已成功标记为已清账！\n"
            "=" * 40 + "\n"
            f"📝 消费描述：{target_bill['consumption_desc']}\n"
            f"💰 总金额：{target_bill['total_amount']}元\n"
            f"👥 参与人：{', '.join(target_bill['participants'])}\n"
            f"⏰ 清账时间：{clear_time}\n"
            f"🧑 清账人：{clearer_name}\n"
            "=" * 40 + "\n"
            "💡 查看清账记录：/aa settlement"
        )
        yield event.plain_result(result)

    # ---------------------- 核心功能：债务明细 ----------------------
    @aa_main_group.command("debt")
    async def show_debt_details(self, event: AstrMessageEvent, bill_id: str):
        """
        查看账单债务明细（谁该给谁多少钱）
        指令格式：/aa debt [账单ID]
        示例：/aa debt abc123（查看ID为abc123的账单债务明细）
        """
        user_id = event.get_sender_id()
        user_bills = self.aa_bills.get(user_id, [])

        # 查找目标账单
        target_bill = None
        for bill in user_bills:
            if bill["bill_id"] == bill_id:
                target_bill = bill
                break

        # 账单不存在的处理
        if not target_bill:
            yield event.plain_result(f"❌ 未找到ID为「{bill_id}」的AA账单\n"
                                    "💡 查看所有账单：/aa list")
            return

        # 构建债务明细输出
        status_tag = "🔴 待清账" if target_bill["status"] == "pending" else "🟢 已清账"
        result = (
            f"📊 账单「{bill_id}」债务明细 | {status_tag}\n"
            "=" * 40 + "\n"
            f"📝 消费描述：{target_bill['consumption_desc']}\n"
            f"💸 付款人：{target_bill['payer']['name']}（垫付{target_bill['total_amount']}元）\n"
            f"🧮 每人应摊：{target_bill['per_person_amount']}元\n"
            "\n【债务关系】\n"
        )

        # 遍历债务明细（除了付款人，其他人都需要给付款人钱）
        debt_details = target_bill["debt_details"]
        if not debt_details:
            result += "⚠️  无债务关系（可能只有付款人一人参与）\n"
        else:
            for debt in debt_details:
                result += f"👉 {debt['debtor']} 应支付 {debt['creditor']} {debt['amount']}元\n"

        # 补充分账误差说明（如有）
        if target_bill["amount_diff"] > 0:
            result += (
                f"\n⚠️  分账误差说明：\n"
                f"由于总金额（{target_bill['total_amount']}元）无法被参与人数（{target_bill['total_people']}人）均分，\n"
                f"付款人{target_bill['payer']['name']}多承担{target_bill['amount_diff']}元误差\n"
            )

        # 补充状态提示
        if target_bill["status"] == "pending":
            result += f"\n💡 提示：所有债务人完成付款后，可标记清账：/aa clear {bill_id}\n"
        else:
            result += f"\n✅ 该账单已在{target_bill['clear_time']}由{target_bill['clearer']['name']}标记为已清账\n"

        yield event.plain_result(result)

    # ---------------------- 辅助功能：清账记录 ----------------------
    @aa_main_group.command("settlement")
    async def list_settlement_records(self, event: AstrMessageEvent):
        """
        查看清账记录
        指令格式：/aa settlement
        """
        user_id = event.get_sender_id()
        user_records = self.settlement_records.get(user_id, [])
        
        # 无清账记录的处理
        if not user_records:
            yield event.plain_result(
                "📜 暂无清账记录\n"
                "💡 标记清账：/aa clear [账单ID]（示例：/aa clear abc123）\n"
                "查看待清账账单：/aa list pending"
            )
            return

        # 按清账时间倒序排序（最新的在前）
        sorted_records = sorted(
            user_records, 
            key=lambda x: x["timestamp"], 
            reverse=True
        )[:10]  # 最多显示10条

        # 构建清账记录输出
        result = f"🟢 清账记录（共{len(user_records)}条，显示最近10条）\n" + "-" * 50 + "\n"
        for idx, record in enumerate(sorted_records, 1):
            result += (
                f"{idx}. 记录ID：{record['record_id']}\n"
                f"   关联账单：{record['bill_id']}（{record['bill_desc']}）\n"
                f"   总金额：{record['total_amount']}元\n"
                f"   清账人：{record['clearer']['name']}\n"
                f"   清账时间：{record['clear_time']}\n"
                "-" * 50 + "\n"
            )

        yield event.plain_result(result)

    # ---------------------- 辅助功能：帮助中心 ----------------------
    @aa_main_group.command("help")
    async def show_aa_help(self, event: AstrMessageEvent):
        """
        显示AA分账系统帮助
        指令格式：/aa help
        """
        help_text = (
            "📊 专业AA分账系统帮助（v2.0.0）\n"
            "=" * 40 + "\n"
            "【核心功能指令】\n"
            "1. 创建账单：\n"
            "   /aa create [参与人1] [参与人2] ... [总金额] [消费描述]\n"
            "   示例：/aa create 张三 李四 王五 600 聚餐\n"
            "\n"
            "2. 查看账单：\n"
            "   /aa list（查看所有账单）\n"
            "   /aa list pending（仅查看待清账）\n"
            "   /aa list cleared（仅查看已清账）\n"
            "\n"
            "3. 标记清账：\n"
            "   /aa clear [账单ID]\n"
            "   示例：/aa clear abc123（标记ID为abc123的账单为已清账）\n"
            "\n"
            "4. 查看债务：\n"
            "   /aa debt [账单ID]\n"
            "   示例：/aa debt abc123（查看该账单的债务明细）\n"
            "\n"
            "5. 清账记录：\n"
            "   /aa settlement（查看所有已清账的记录）\n"
            "\n"
            "【注意事项】\n"
            "- 金额支持小数（如25.5元），必须为正数\n"
            "- 参与人无需重复输入（系统会自动去重）\n"
            "- 付款人（指令发送者）会自动加入参与人列表\n"
            "- 分账误差由付款人承担（确保总金额正确）\n"
            "=" * 40
        )
        yield event.plain_result(help_text)

    # ---------------------- 工具方法：生成债务明细 ----------------------
    def _generate_debt_details(self, payer_name: str, participants: List[str], per_person: float) -> List[Dict]:
        """
        生成债务明细（谁该给谁多少钱）
        :param payer_name: 付款人名称
        :param participants: 参与人列表
        :param per_person: 每人分摊金额
        :return: 债务明细列表（debtor=债务人，creditor=债权人，amount=金额）
        """
        debt_details = []
        for person in participants:
            if person != payer_name:  # 除了付款人，其他人都是债务人
                debt_details.append({
                    "debtor": person,
                    "creditor": payer_name,
                    "amount": per_person
                })
        return debt_details

    # ---------------------- 数据持久化：加载与保存 ----------------------
    def _load_bills_data(self):
        """加载AA账单数据"""
        try:
            if os.path.exists(self.bills_data_path):
                with open(self.bills_data_path, "r", encoding="utf-8") as f:
                    self.aa_bills = json.load(f)
                logger.info(f"成功加载AA账单数据，共{len(self.aa_bills)}个用户的账单")
            else:
                logger.info("AA账单数据文件不存在，初始化空数据")
                self.aa_bills = {}
        except Exception as e:
            logger.error(f"加载AA账单数据失败：{str(e)}，初始化空数据")
            self.aa_bills = {}

    def _save_bills_data(self):
        """保存AA账单数据"""
        try:
            with open(self.bills_data_path, "w", encoding="utf-8") as f:
                json.dump(self.aa_bills, f, ensure_ascii=False, indent=2)
            logger.info("AA账单数据保存成功")
        except Exception as e:
            logger.error(f"保存AA账单数据失败：{str(e)}")

    def _load_settlement_data(self):
        """加载清账记录数据"""
        try:
            if os.path.exists(self.settlement_data_path):
                with open(self.settlement_data_path, "r", encoding="utf-8") as f:
                    self.settlement_records = json.load(f)
                logger.info(f"成功加载清账记录数据，共{len(self.settlement_records)}个用户的记录")
            else:
                logger.info("清账记录数据文件不存在，初始化空数据")
                self.settlement_records = {}
        except Exception as e:
            logger.error(f"加载清账记录数据失败：{str(e)}，初始化空数据")
            self.settlement_records = {}

    def _save_settlement_data(self):
        """保存清账记录数据"""
        try:
            with open(self.settlement_data_path, "w", encoding="utf-8") as f:
                json.dump(self.settlement_records, f, ensure_ascii=False, indent=2)
            logger.info("清账记录数据保存成功")
        except Exception as e:
            logger.error(f"保存清账记录数据失败：{str(e)}")

    # ---------------------- 插件卸载时的数据保存 ----------------------
    async def terminate(self):
        """插件卸载时触发，确保数据持久化"""
        self._save_bills_data()
        self._save_settlement_data()
        logger.info("AA分账系统插件已卸载，所有数据已保存")
