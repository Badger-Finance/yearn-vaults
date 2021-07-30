// SPDX-License-Identifier: MIT
pragma solidity ^0.6.12;

import "deps/@openzeppelin/contracts-upgradeable/math/SafeMathUpgradeable.sol";
import "deps/@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "deps/@openzeppelin/contracts-upgradeable/cryptography/MerkleProofUpgradeable.sol";
import "deps/@openzeppelin/contracts-upgradeable/token/ERC20/SafeERC20Upgradeable.sol";
import "deps/@openzeppelin/contracts-upgradeable/token/ERC20/ERC20Upgradeable.sol";
import {VaultAPI} from "./BaseStrategy.sol";

contract BadgerBouncer is OwnableUpgradeable {
    using SafeMathUpgradeable for uint256;
    using SafeERC20Upgradeable for IERC20Upgradeable;

    mapping (address => uint256) public userCaps;
    mapping (address => uint256) public totalCaps;
    mapping (address => bytes32) public guestListRootOverride;
    mapping (address => bool) public removedGuestList;
    mapping (address => bool) public isBanned;
    mapping (address => mapping (address => bool)) public vaultGuests;

    bytes32 public defaultGuestListRoot;

    event SetDefaultGuestListRoot(bytes32 indexed defaultGuestListRoot);
    event Deposit(address vault, uint256 amount, address user);
    event DepositFor(address vault, uint256 amount, address recipient);
    event Banned(address account);
    event Unbanned(address account);
    event SetRootForVault(address vault, bytes32 guestListRoot);
    event RemoveRootForVault(address vault);
    event ProveInvitation(address vault, address account, bytes32 guestRoot);
    event SetUserDepositCap(address vault, uint256 usercap);
    event SetTotalDepositCap(address vault, uint256 totalcap);

    uint256 constant MAX_UINT256 = 2**256 - 1;

    /**
     * @notice Create the Badger Bouncer, setting the message sender as
     * `owner`.
     */
    function initialize(bytes32 defaultGuestListRoot_) public initializer {
        __Ownable_init();
        defaultGuestListRoot = defaultGuestListRoot_;
    }

    /// ===== View Functions =====

    function remainingTotalDepositAllowed(address vault) public view returns (uint256) {
        uint256 totalDepositCap = totalCaps[vault];
        // If total cap is set to 0, treat as no cap
        if (totalDepositCap == 0) {
            return MAX_UINT256;
        } else {
            return totalDepositCap.sub(VaultAPI(vault).totalAssets());
        }
    }

    function remainingUserDepositAllowed(address user, address vault) public view returns (uint256) {
        uint256 userDepositCap = userCaps[vault];
        // If user cap is set to 0, treat as no cap
        if (userDepositCap == 0) {
            return MAX_UINT256;
        } else {
            ERC20Upgradeable token = ERC20Upgradeable(VaultAPI(vault).token());
            return userDepositCap.sub(VaultAPI(vault).balanceOf(user).mul(10 ** uint8(token.decimals())).div(VaultAPI(vault).pricePerShare()));
        }
    }

    /// ===== Public Actions =====

    /**
     * @notice Sets the default GuestList merkle root to a new value
     */
    function setDefaultGuestListRoot(bytes32 defaultGuestListRoot_) external onlyOwner {
        defaultGuestListRoot = defaultGuestListRoot_;

        emit SetDefaultGuestListRoot(defaultGuestListRoot);
    }

    /**
     * @notice Sets an specified Merkle root for a certain vault
     */
    function setRootForVault(address vault, bytes32 guestListRoot) external onlyOwner {
        guestListRootOverride[vault] = guestListRoot;
        removedGuestList[vault] = false;

        emit SetRootForVault(vault, guestListRoot);
    }

    /**
     * @notice Sets a vault's Merkle root to 0x0
     */
    function removeRootForVault(address vault) external onlyOwner {
        guestListRootOverride[vault] = bytes32(0);
        removedGuestList[vault] = true;

        emit RemoveRootForVault(vault);
    }

    /**
     * @notice Invite guests or kick them from the party for an specific vault.
     * @param vault The vault in matter.
     * @param guests The guests to add or update.
     * @param invited A flag for each guest at the matching index, inviting or
     * uninviting the guest.
     * @notice the guests and invited arrays must have matching lengths.
     */
    function setVaultGuests(address vault, address[] calldata guests, bool[] calldata invited) external onlyOwner {
        _setVaultGuests(vault, guests, invited);
    }

    /**
     * @notice Adds given address to the blacklist
     */
    function banAddress(address account) external onlyOwner {
        isBanned[account] = true;

        emit Banned(account);
    }

    /**
     * @notice Removes given address from the blacklist
     */
    function unbanAddress(address account) external onlyOwner {
        isBanned[account] = false;

        emit Unbanned(account);
    }

    /**
     * @notice Sets user deposit cap for a give vault
     */
    function setUserDepositCap(address vault, uint256 cap) external onlyOwner {
        userCaps[vault] = cap;

        emit SetUserDepositCap(vault, cap);
    }

    /**
     * @notice Sets total deposit cap for a give vault
     */
    function setTotalDepositCap(address vault, uint256 cap) external onlyOwner {
        totalCaps[vault] = cap;

        emit SetTotalDepositCap(vault, cap);
    }

    /**
     * @notice Deposits into vault with merkle proof verification
     */
    function deposit(address vault, uint256 amount, bytes32[] calldata merkleProof) external {
        _deposit(vault, amount, merkleProof);
    }

    /**
     * @notice Variation: Deposits into vault without merkle proof verification
     */
    function deposit(address vault, uint256 amount) external {
        _deposit(vault, amount, new bytes32[](0));
    }

    /**
     * @notice Variation: Deposits all balance into vault without merkle proof verification
     */
    function deposit(address vault) external {
        _deposit(vault, IERC20Upgradeable(VaultAPI(vault).token()).balanceOf(msg.sender), new bytes32[](0));
    }

    /**
     * @notice Deposits into vault for an specific user with merkle proof verification
     */
    function depositFor(address vault, address recipient, uint256 amount, bytes32[] calldata merkleProof) external {
        _depositFor(vault, recipient, amount, merkleProof);
    }

    /**
     * @notice Deposits into vault for an specific user without merkle proof verification
     */
    function depositFor(address vault, address recipient, uint256 amount) external {
        _depositFor(vault, recipient, amount, new bytes32[](0));
    }

    /**
     * @notice Permissionly prove an address is included in a given vault's merkle root, thereby granting access
     * @notice Note that the list is designed to ONLY EXPAND in future instances
     * @notice The admin does retain the ability to ban individual addresses
     * @param vault The vault in matter.
     * @param account The account's address to check.
     * @param merkleProof The Merkle proof used to verify access.
     */
    function proveInvitation(address vault, address account, bytes32[] calldata merkleProof) external {
        bytes32 guestRoot = _getVaultGuestListRoot(vault);
        // Verify Merkle Proof
        require(_verifyInvitationProof(account, guestRoot, merkleProof), "Guestlist verification");

        address[] memory accounts = new address[](1);
        bool[] memory invited = new bool[](1);

        accounts[0] = account;
        invited[0] = true;

        _setVaultGuests(vault, accounts, invited);

        emit ProveInvitation(vault, account, guestRoot);
    }

    /**
     * @notice Check if a guest with a bag of a certain size is allowed into
     * the party.
     * @param guest The guest's address to check.
     * @param vault The vault's whose access to authorize.
     * @param amount The amount intended to deposit, to be verified against deposit bounds.
     * @param merkleProof The Merkle proof used to verify access.
     */
    function authorized(
        address guest,
        address vault,
        uint256 amount,
        bytes32[] memory merkleProof
    ) public view returns (bool)
    {
        // Check if guest has been manually added or invitation previously verified
        bool invited = vaultGuests[vault][guest];
        bytes32 guestRoot = _getVaultGuestListRoot(vault);

        // If there is no guest root, all users are invited
        if (!invited && guestRoot == bytes32(0)) {
            invited = true;
        }

        // If the user is not already invited and there is an active guestList,
        // require verification of merkle proof to grant temporary invitation (does not set storage variable)
        if (!invited && guestRoot != bytes32(0)) {
            // Will revert on invalid proof
            invited = _verifyInvitationProof(guest, guestRoot, merkleProof);
        }

        // If the guest proved invitiation via list, verify if the amount to deposit keeps them under the cap
        if (invited && remainingUserDepositAllowed(guest, vault) >= amount && remainingTotalDepositAllowed(vault) >= amount) {
            return true;
        } else {
            return false;
        }
    }

    /// ===== Internal Implementations =====

    function _getVaultGuestListRoot(address vault) internal view returns (bytes32) {
        bytes32 guestRoot;
        // If vault's root is 0x0 and it has been removed: guestlist has been removed -> return 0x0
        if (guestListRootOverride[vault] == bytes32(0) && removedGuestList[vault] == true) {
            guestRoot = bytes32(0);
        // If vault's root is 0x0 and but it hasn't been removed -> use default Merkle root
        } else if (guestListRootOverride[vault] == bytes32(0) && removedGuestList[vault] == false) {
            guestRoot = defaultGuestListRoot;
        // Else return the specific vault's Merkle root
        } else {
            guestRoot = guestListRootOverride[vault];
        }
        return guestRoot;
    }

    function _setVaultGuests(address vault, address[] memory _guests, bool[] memory _invited) internal {
        require(_guests.length == _invited.length, "Input arrays' length mismatch");
        for (uint256 i = 0; i < _guests.length; i++) {
            if (_guests[i] == address(0)) {
                break;
            }
            vaultGuests[vault][_guests[i]] = _invited[i];
        }
    }

    function _verifyInvitationProof(address account, bytes32 guestRoot, bytes32[] memory merkleProof) internal pure returns (bool) {
        bytes32 node = keccak256(abi.encodePacked(account));
        return MerkleProofUpgradeable.verify(merkleProof, guestRoot, node);
    }

    /**
     * @notice Verifies permission criteria and redirects deposit to designated vault if authorized
     */
    function _deposit(address vault, uint256 amount, bytes32[] memory merkleProof) internal {
        require(authorized(msg.sender, vault, amount, merkleProof), "Unauthorized user for given vault");
        require(isBanned[msg.sender] == false, "Blacklisted user");

        IERC20Upgradeable token = IERC20Upgradeable(VaultAPI(vault).token());

        if (token.allowance(address(this), address(vault)) < amount) {
            token.safeApprove(address(vault), 0); // Avoid issues with some tokens requiring 0
            token.safeApprove(address(vault), MAX_UINT256);
        }

        token.safeTransferFrom(msg.sender, address(this), amount);

        VaultAPI(vault).deposit(amount, msg.sender);

        emit Deposit(vault, amount, msg.sender);
    }

    /**
     * @notice Verifies permission criteria for a specificed user and redirects deposit to designated vault if authorized
     */
    function _depositFor(address vault, address recipient, uint256 amount, bytes32[] memory merkleProof) internal {
        require(authorized(recipient, vault, amount, merkleProof), "Unauthorized user for given vault");
        require(isBanned[recipient] == false, "Blacklisted user");

        IERC20Upgradeable token = IERC20Upgradeable(VaultAPI(vault).token());

        if (token.allowance(address(this), address(vault)) < amount) {
            token.safeApprove(address(vault), 0); // Avoid issues with some tokens requiring 0
            token.safeApprove(address(vault), MAX_UINT256);
        }

        token.safeTransferFrom(msg.sender, address(this), amount);

        VaultAPI(vault).deposit(amount, recipient);

        emit DepositFor(vault, amount, recipient);
    }
}