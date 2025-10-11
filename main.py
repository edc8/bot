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
    "2.1.0"            # 版本
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
    @filter.command("aa")
    async def aa_main_command(self, event: AstrMessageEvent, *args):
        """
        AA分账主指令，支持以下子命令：
        - /aa [参与人] [金额] - 创建AA账单（例如：/aa 陈 100）
        - /aa 查 - 查看所有账单
        - /aa 对账 [账单ID] - 查看指定账单的债务明细
        - /aa 清账 [账单ID] - 标记指定账单为已清账
        - /aa 帮助 - 显示帮助信息
        """
        if not args:
            yield event.plain_result(self._get_help_text())
            return
            
        sub_command = args[0]
        
        # 创建账单：/aa [参与人] [金额]
        if sub_command != "查" and sub_command != "对账" and sub_command != "清账" and sub_command != "帮助":
            await self.create_aa_bill(event, *args)
        # 查看账单列表：/aa 查
        elif sub_command == "查":
            await self.list_aa_bills(event)
        # 查看债务明细：/aa 对账 [账单ID]
        elif sub_command == "对账":
            if len(args) < 2:
                yield event.plain_result("❌ 请指定账单ID！\n用法：/aa 对账 [账单ID]\n示例：/aa 对账 abc123")
                return
            await self.show_debt_details(event, args[1])
        # 标记清账：/aa 清账 [账单ID]
        elif sub_command == "清账":
            if len(args) < 2:
                yield event.plain_result("❌ 请指定账单ID！\n用法：/aa 清账 [账单ID]\n示例：/aa 清账 abc123")
                return
            await self.clear_aa_bill(event, args[1])
        # 帮助信息
        elif sub_command == "帮助":
            yield event.plain_result(self._get_help_text())
        else:
            yield event.plain_result(f"❌ 未知命令：{sub_command}\n{self._get_help_text()}")

    # ---------------------- 核心功能：账单创建 ----------------------
    async def create_aa_bill(self, event: AstrMessageEvent, *args):
        """
        创建AA账单
        指令格式：/aa [参与人1] [参与人2] ... [总金额] [消费描述可选]
        示例：/aa 陈 100（简单模式）、/aa 张三 李四 600 聚餐（带描述）
        """
        # 基础参数验证
        if len(args) < 2:
            yield event.plain_result(
                "❌ 指令格式错误！正确用法：\n"
                "📌 简单模式：/aa [参与人] [总金额]\n"
                "   示例：/aa 陈 100\n"
                "📌 完整模式：/aa [参与人1] [参与人2] ... [总金额] [消费描述]\n"
                "   示例：/aa 张三 李四 600 聚餐"
            )
            return

        # 解析参数
        try:
            # 尝试解析金额（最后一个或倒数第二个参数）
            # 先假设金额是最后一个参数
            amount_index = -1
            total_amount = float(args[amount_index])
            
            # 如果金额解析成功，判断是否有消费描述
            if total_amount <= 0:
                raise ValueError("总金额必须大于0")
                
            # 检查是否有消费描述（如果金额是最后一个参数且前面至少有一个参与人）
            if len(args) >= 3:
                # 尝试判断倒数第二个参数是否是金额（处理可能的描述中有数字的情况）
                try:
                    # 如果倒数第二个参数也能转成数字，认为金额是最后一个参数
                    float(args[-2])
                except ValueError:
                    # 倒数第二个参数不是数字，说明金额是倒数第二个参数，最后一个是描述
                    amount_index = -2
                    total_amount = float(args[amount_index])
                    if total_amount <= 0:
                        raise ValueError("总金额必须大于0")
            
            # 提取参与人、金额和描述
            total_amount = float(args[amount_index])
            participants = list(args[:amount_index])
            consumption_desc = " ".join(args[amount_index+1:]) if (amount_index+1 < len(args)) else "日常消费"
            
        except ValueError as e:
            yield event.plain_result(f"❌ 金额错误：{str(e)}（请输入正数，支持小数）")
            return

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
            f"  1. 查看账单：/aa 查\n"
            f"  2. 标记清账：/aa 清账 {bill_id}\n"
            f"  3. 查看债务：/aa 对账 {bill_id}"
        )
        yield event.plain_result(result)

    # ---------------------- 核心功能：账单管理 ----------------------
    async def list_aa_bills(self, event: AstrMessageEvent):
        """
        查看AA账单列表
        指令格式：/aa 查
        """
        user_id = event.get_sender_id()
        user_bills = self.aa_bills.get(user_id, [])
        
        # 无账单时的提示
        if not user_bills:
            yield event.plain_result(
                "📋 暂无AA账单\n"
                "💡 点击创建：/aa [参与人] [金额]\n"
                "示例：/aa 张三 300"
            )
            return

        # 按创建时间倒序排序（最新的在前）
        sorted_bills = sorted(
            user_bills, 
            key=lambda x: x["create_timestamp"], 
            reverse=True
        )[:10]  # 最多显示10条（避免信息过长）

        # 统计待清账和已清账数量
        pending_count = len([b for b in user_bills if b["status"] == "pending"])
        cleared_count = len([b for b in user_bills if b["status"] == "cleared"])
        title = f"📊 所有AA账单（待清账：{pending_count}条 | 已清账：{cleared_count}条）"

        # 构建账单列表输出
        result = title + "\n" + "-" * 50 + "\n"
        for idx, bill in enumerate(sorted_bills, 1):
            status_tag = "🔴 待清账" if bill["status"] == "pending" else "🟢 已清账"
            clear_info = f"清账时间：{bill['clear_time']}" if bill["status"] == "cleared" else f"操作：/aa 清账 {bill['bill_id']}"
            
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
            result += "⚠️  仅显示最近10条账单\n"
        result += "💡 查看债务明细：/aa 对账 [账单ID]（示例：/aa 对账 abc123）"
        
        yield event.plain_result(result)

    async def clear_aa_bill(self, event: AstrMessageEvent, bill_id: str):
        """
        标记AA账单为已清账
        指令格式：/aa 清账 [账单ID]
        示例：/aa 清账 abc123（将ID为abc123的账单标记为已清账）
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
                                    "💡 查看所有账单：/aa 查")
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
            "=" * 40
        )
        yield event.plain_result(result)

    # ---------------------- 核心功能：债务明细 ----------------------
    async def show_debt_details(self, event: AstrMessageEvent, bill_id: str):
        """
        查看账单债务明细（谁该给谁多少钱）
        指令格式：/aa 对账 [账单ID]
        示例：/aa 对账 abc123（查看ID为abc123的账单债务明细）
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
                                    "💡 查看所有账单：/aa 查")
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
            result += f"\n💡 提示：所有债务人完成付款后，可标记清账：/aa 清账 {bill_id}\n"
        else:
            result += f"\n✅ 该账单已在{target_bill['clear_time']}由{target_bill['clearer']['name']}标记为已清账\n"

        yield event.plain_result(result)

    # ---------------------- 辅助功能：帮助信息 ----------------------
    def _get_help_text(self):
        """获取帮助信息文本"""
        return (
            "📊 AA分账系统帮助（v2.1.0）\n"
            "=" * 40 + "\n"
            "【可用指令】\n"
            "1. 创建账单：\n"
            "   /aa [参与人1] [参与人2] ... [金额] [描述可选]\n"
            "   示例：/aa 陈 100（简单模式）\n"
            "   示例：/aa 张三 李四 600 聚餐（带描述）\n"
            "\n"
            "2. 查看账单：\n"
            "   /aa 查\n"
            "\n"
            "3. 标记清账：\n"
            "   /aa 清账 [账单ID]\n"
            "   示例：/aa 清账 abc123\n"
            "\n"
            "4. 查看债务明细：\n"
            "   /aa 对账 [账单ID]\n"
            "   示例：/aa 对账 abc123\n"
            "\n"
            "5. 查看帮助：\n"
            "   /aa 帮助\n"
            "=" * 40
        )

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
