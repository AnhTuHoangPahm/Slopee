CREATE TABLE IF NOT EXISTS users (
	id varchar(36) PRIMARY KEY,
	role enum ('admin', 'seller', 'user') NOT NULL,
	name varchar(50) NOT NULL,
	email varchar(50) NOT NULL UNIQUE,
	phone char(10) NOT NULL UNIQUE,
	bio text,
    deletionRequestedAt timestamp NULL DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS credentials (
	userId varchar(36) NOT NULL,
	username varchar(25) NOT NULL PRIMARY KEY check (length(username) > 3),
	passwordHash varchar(256) NOT NULL,
	passwordSalt varchar(256) NOT NULL,
    passPhraseHash varchar(256) comment '6-digit pass phrase for payments',
    foreign key (userId) references users (id) on delete cascade
);

CREATE TABLE IF NOT EXISTS shops (
    id varchar(36) PRIMARY KEY,
    sellerId varchar(36) NOT NULL UNIQUE,
    name varchar(100) NOT NULL,
    description text,
    avatarUrl varchar(500),
    createdAt timestamp default current_timestamp,
    foreign key (sellerId) references users (id) on delete cascade
);

CREATE TABLE IF NOT EXISTS paymentMethods (
    id varchar(36) PRIMARY KEY,
    userId varchar(36) NOT NULL,
    methodType enum ('bank', 'credit_card', 'cash') NOT NULL,
    providerName varchar(100) comment 'e.g. Bank A, Bank B, Visa',
    accountNumber varchar(50),
    balance decimal(15,0) NOT NULL default 0 comment 'Số dư (VND)',
    foreign key (userId) references users (id) on delete cascade
);

CREATE TABLE IF NOT EXISTS categories (
	id int unsigned auto_increment PRIMARY KEY,
    name text NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
	id varchar(15) PRIMARY KEY,
	categoryId int unsigned NOT NULL,
    shopId varchar(36) NOT NULL,      
    name varchar(255) NOT NULL,       
    description text,                 
    inStock int NOT NULL check (inStock >= 0),
    unitPrice DECIMAL(15, 0) NOT NULL check (unitPrice >=0),
    isActive boolean default true comment 'is product still for sale?',
	foreign key (categoryId) references categories (id),
    foreign key (shopId) references shops (id) on delete cascade
);

CREATE TABLE IF NOT EXISTS productImages (
    id varchar(36) PRIMARY KEY,
    productId varchar(15) NOT NULL,
    imageUrl varchar(500) NOT NULL,
    isPrimary boolean default false,
    foreign key (productId) references products (id) on delete cascade
);

CREATE TABLE IF NOT EXISTS productVariants (
    id varchar(36) PRIMARY KEY,
    productId varchar(15) NOT NULL,
    variantName varchar(100) NOT NULL,
    variantValue varchar(100) NOT NULL,
    foreign key (productId) references products (id) on delete cascade
);

CREATE TABLE IF NOT EXISTS reviews (
	id varchar(36) PRIMARY KEY,
    userId varchar(36) NOT NULL,
    productId varchar(15) NOT NULL,
    rating int NOT NULL check (rating >= 1 and rating <= 5), 
    comment mediumtext,
    createdAt timestamp NOT NULL default current_timestamp,
    foreign key (productId) references products (id) on delete cascade, 
    foreign key (userId) references users (id) on delete restrict 
);

CREATE TABLE IF NOT EXISTS reviewImages (
    id varchar(36) PRIMARY KEY,
    reviewId varchar(36) NOT NULL,
    imageUrl varchar(500) NOT NULL,
    foreign key (reviewId) references reviews (id) on delete cascade
);

CREATE TABLE IF NOT EXISTS carts (
	id varchar(36) PRIMARY KEY,
	userId varchar(36) NOT NULL,
    createdAt timestamp NOT NULL DEFAULT current_timestamp,
    status enum ('active', 'ordered') NOT NULL default 'active',
	foreign key (userId) references users (id) on delete cascade
);

CREATE TABLE IF NOT EXISTS cartItems (
	id varchar(36) primary key,
	cartId varchar(36) NOT NULL,
    productId varchar(15) NOT NULL,
    selectedVariants text,            
	quantity int NOT NULL check (quantity > 0),
	foreign key (cartId) references carts (id) on delete cascade,
	foreign key (productId) references products (id) on delete restrict 
);

CREATE TABLE IF NOT EXISTS orders (
	id varchar(36) PRIMARY KEY,
	userId varchar(36) NOT NULL,
    paymentMethodId varchar(36),      
	created_at timestamp NOT NULL DEFAULT current_timestamp,
    status enum('pending', 'paid', 'shipped', 'cancelled', 'received') NOT NULL default 'pending',
    totalAmount decimal(15, 0) NOT NULL default 0,
    foreign key (userId) references users(id) on delete restrict,
    foreign key (paymentMethodId) references paymentMethods(id) on delete set null
);

CREATE TABLE IF NOT EXISTS orderLines (
	id varchar(36) PRIMARY KEY,
	orderId varchar(36),
	productId varchar(15) NOT NULL,
    selectedVariants text,            
    unitPrice decimal(15, 0) NOT NULL,
	quantity int NOT NULL CHECK (quantity > 0),
    snapshotProductName varchar(255),
    snapshotShopName varchar(255),
    FOREIGN KEY (orderId) REFERENCES orders (id) on delete cascade,
    FOREIGN KEY (productId) REFERENCES products (id) on delete restrict 
);

CREATE TABLE IF NOT EXISTS reviews (
    id varchar(36) PRIMARY KEY,
    userId varchar(36) NOT NULL,
    productId varchar(15) NOT NULL,
    rating int NOT NULL check (rating >= 1 AND rating <= 5),
    comment text NOT NULL,
    createdAt timestamp NOT NULL DEFAULT current_timestamp,
    FOREIGN KEY (userId) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (productId) REFERENCES products(id) ON DELETE CASCADE,
    CONSTRAINT uniqueReview UNIQUE(userId, productId)
);

CREATE TABLE IF NOT EXISTS reviewImages (
    id int auto_increment PRIMARY KEY,
    reviewId varchar(36) NOT NULL,
    imageUrl varchar(500) NOT NULL,
    FOREIGN KEY (reviewId) REFERENCES reviews(id) ON DELETE CASCADE
);
